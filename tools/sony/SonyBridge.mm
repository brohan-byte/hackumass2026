// GhostUI bridge to mos9527/SonyHeadphonesClient's public C ABI.
// A worker owns the protocol; the main thread services macOS Bluetooth callbacks.
#import <Foundation/Foundation.h>
#import <IOBluetooth/IOBluetooth.h>
#include <mdr-c/Headphones.h>
#include <mdr-bt/ConnectionMacOS.h>
#include <chrono>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

using Clock=std::chrono::steady_clock;
static NSString* string(const char* text) { return [NSString stringWithUTF8String:text] ?: @""; }
static void emit(NSDictionary* object) {
    NSData* data=[NSJSONSerialization dataWithJSONObject:object options:0 error:nil];
    std::cout.write((const char*)data.bytes,data.length);std::cout << std::endl;
}
static bool check(MDRResult code,const char* action) {
    if(code==MDR_RESULT_OK)return true;
    emit(@{@"error":[NSString stringWithFormat:@"%s: %s",action,mdrResultString(code)]});return false;
}
struct Session {
    MDRConnectionMacOS* backend=mdrConnectionMacOSCreate();
    MDRConnection* connection=mdrConnectionMacOSGet(backend);
    MDRHeadphones* headphones=nullptr;
    ~Session() {
        if(headphones)mdrHeadphonesDestroy(headphones);
        if(backend)mdrConnectionMacOSDestroy(backend);
    }
    bool waitReady(int seconds=15) {
        auto deadline=Clock::now()+std::chrono::seconds(seconds);
        while(Clock::now()<deadline) {
            MDREvent event=MDR_EVENT_NONE;
            if(!check(mdrHeadphonesPoll(headphones,&event),"Sony protocol"))return false;
            if(mdrHeadphonesIsInitialized(headphones) && mdrHeadphonesIsReady(headphones))return true;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        emit(@{@"error":@"Sony initialization/readback timed out. Close Sound Connect and retry."});return false;
    }
    NSString* text(MDRText field) {
        char buffer[1024]={};uint32_t count=sizeof(buffer);
        if(mdrHeadphonesGetText(headphones,field,0,buffer,&count)!=MDR_RESULT_OK)return @"";
        return string(buffer);
    }
    NSArray* devices() {
        MDRDeviceInfo* list=nullptr;int count=0;
        auto deadline=Clock::now()+std::chrono::seconds(5);
        MDRResult code;
        do {
            code=mdrConnectionGetDevicesList(connection,&list,&count);
            if(code!=MDR_RESULT_INPROGRESS)break;
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }while(Clock::now()<deadline);
        if(code!=MDR_RESULT_OK) { check(code,"List paired headphones");return nil; }
        NSMutableArray* result=[NSMutableArray array];
        for(int i=0;i<count;i++) {
            NSString* name=string(list[i].szDeviceName);
            if([name localizedCaseInsensitiveContainsString:@"WH-1000XM5"] ||
               [name localizedCaseInsensitiveContainsString:@"WF-1000XM5"])
                [result addObject:@{@"name":name,@"address":string(list[i].szDeviceMacAddress)}];
        }
        mdrConnectionFreeDevicesList(connection,&list);return result;
    }
    bool connect(const std::string& requested) {
        std::string address=requested;
        NSArray* list=devices();if(!list)return false;
        if(address.empty()) {
            if(list.count!=1) {
                emit(@{@"error":list.count==0 ? @"No paired Sony XM5 found. Pair/connect the headphones to this Mac first." :
                       @"Multiple paired XM5 devices found. Supply the intended Bluetooth address.",@"devices":list});return false;
            }
            address=[list[0][@"address"] UTF8String];
        } else {
            bool known=false;
            for(NSDictionary* item in list)if([item[@"address"] caseInsensitiveCompare:string(address.c_str())]==NSOrderedSame)known=true;
            if(!known) { emit(@{@"error":@"That address is not a paired WH/WF-1000XM5 on this Mac."});return false; }
        }
        MDRResult code=mdrConnectionConnect(connection,address.c_str(),MDR_SERVICE_UUID_V2);
        if(code!=MDR_RESULT_OK && code!=MDR_RESULT_INPROGRESS)return check(code,"Connect Sony");
        auto deadline=Clock::now()+std::chrono::seconds(12);
        do {
            code=mdrConnectionPoll(connection,100);
            if(code==MDR_RESULT_OK)break;
            if(code!=MDR_RESULT_INPROGRESS && code!=MDR_RESULT_ERROR_TIMEOUT) {
                emit(@{@"error":string(mdrConnectionGetLastError(connection))});return false;
            }
        }while(Clock::now()<deadline);
        if(code!=MDR_RESULT_OK) { emit(@{@"error":@"Sony Bluetooth connection timed out."});return false; }
        if(!check(mdrHeadphonesCreate(MDR_ABI_VERSION,connection,MDR_PROTOCOL_V2,&headphones),"Create Sony session"))return false;
        mdrHeadphonesSetTimeout(headphones,MDR_TIMEOUT_DEFAULT,5000);
        mdrHeadphonesSetTimeout(headphones,MDR_TIMEOUT_ACK_RETRIES,2);
        auto flags=MDR_HEADPHONES_INIT_DISCOVERY | MDR_HEADPHONES_INIT_PLAYBACK | MDR_HEADPHONES_INIT_BATTERY;
        if(!check(mdrHeadphonesRequestInit(headphones,flags),"Read Sony identity/capabilities") || !waitReady())return false;
        NSString* model=text(MDR_TEXT_MODEL_NAME);
        if(![model containsString:@"1000XM5"]) { emit(@{@"error":@"Connected device did not report an XM5 model."});return false; }
        MDRFeatureAvailability feature=MDR_AVAILABILITY_UNKNOWN;
        if(!check(mdrHeadphonesGetFeature(headphones,MDR_FEATURE_PLAYBACK_VOLUME,&feature),"Read volume capability"))return false;
        if(feature!=MDR_AVAILABILITY_AVAILABLE) { emit(@{@"error":@"Sony did not report playback volume control support."});return false; }
        int32_t minimum=0,maximum=0,step=0;
        if(!check(mdrHeadphonesGetValue(headphones,MDR_VALUE_PLAYBACK_VOLUME_MIN,0,&minimum),"Read volume minimum") ||
           !check(mdrHeadphonesGetValue(headphones,MDR_VALUE_PLAYBACK_VOLUME_MAX,0,&maximum),"Read volume maximum") ||
           !check(mdrHeadphonesGetValue(headphones,MDR_VALUE_PLAYBACK_VOLUME_STEP,0,&step),"Read volume step"))return false;
        if(minimum<0 || maximum<=minimum || maximum>1000 || step!=1) { emit(@{@"error":@"Unsupported Sony volume range."});return false; }
        NSString* unique=text(MDR_TEXT_UNIQUE_ID);
        NSDictionary* control=@{@"id":@"volume",@"label":@"Volume",@"type":@"number",@"min":@(minimum),@"max":@(maximum),@"step":@1};
        emit(@{@"address":string(address.c_str()),@"model":model,@"firmware":text(MDR_TEXT_FIRMWARE_VERSION),
               @"capabilities":@{@"deviceId":[@"sony:" stringByAppendingString:string(address.c_str())],
                                 @"name":model,@"controls":@[control]},@"readOnlyProbe":@YES});
        return true;
    }
    NSDictionary* readState() {
        if(!waitReady())return nil;
        if(!check(mdrHeadphonesRequestSync(headphones,MDR_HEADPHONES_SYNC_PLAYBACK),"Refresh Sony playback") || !waitReady())return nil;
        MDRPlayback playback{};
        if(!check(mdrHeadphonesGetPlayback(headphones,MDR_PROPERTY_CURRENT,&playback),"Read Sony volume"))return nil;
        return @{@"volume":@(playback.volume)};
    }
    bool setVolume(int value) {
        int32_t minimum=0,maximum=0;
        mdrHeadphonesGetValue(headphones,MDR_VALUE_PLAYBACK_VOLUME_MIN,0,&minimum);
        mdrHeadphonesGetValue(headphones,MDR_VALUE_PLAYBACK_VOLUME_MAX,0,&maximum);
        if(value<minimum || value>maximum) { emit(@{@"error":@"Volume outside reported range."});return false; }
        if(!waitReady() || !check(mdrHeadphonesSetPlaybackVolume(headphones,value),"Stage Sony volume") ||
           !check(mdrHeadphonesRequestCommit(headphones),"Send Sony volume") || !waitReady())return false;
        // The caller verifies a fresh device-reported value, never DESIRED/ACK.
        return true;
    }
};
int main(int argc,char** argv) {
    // New macOS IOBluetooth uses a lazily created CoreBluetooth coordinator.
    // Prime it and service its initial state event before opening RFCOMM;
    // otherwise the OS rejects the open while that manager is still unknown.
    @autoreleasepool {
        for(IOBluetoothDevice* device in [IOBluetoothDevice pairedDevices]) {
            (void)device.name;(void)device.addressString;(void)device.isConnected;
        }
        NSDate* ready=[NSDate dateWithTimeIntervalSinceNow:2.0];
        while(ready.timeIntervalSinceNow>0) {
            [[NSRunLoop mainRunLoop] runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
        }
    }
    std::string mode=argc>1 ? argv[1] : "--probe";
    std::string address=argc>2 ? argv[2] : "";
    if(mode!="--list" && mode!="--probe" && mode!="--serve") { std::cerr << "Use --list, --probe [MAC] or --serve [MAC]\n";return 2; }
    int result=0;
    std::thread worker([&] {
        @autoreleasepool {
            Session session;
            if(mode=="--list") {
                NSArray* devices=session.devices();if(devices)emit(@{@"devices":devices});else result=1;
            } else if(!session.connect(address))result=1;
            else if(mode=="--probe") {
                NSDictionary* state=session.readState();if(state)emit(@{@"state":state,@"readOnlyProbe":@YES});else result=1;
            } else {
                std::string line;
                while(std::getline(std::cin,line)) {
                    if(line=="quit")break;
                    bool valid=line=="state";
                    if(line.rfind("volume ",0)==0) {
                        try {
                            size_t end=0;int value=std::stoi(line.substr(7),&end);
                            valid=end==line.size()-7 && session.setVolume(value);
                        } catch(...) { valid=false; }
                    }
                    if(!valid) { emit(@{@"error":@"Invalid command or Sony command failed; no automatic replay."});break; }
                    NSDictionary* state=session.readState();if(!state)break;
                    emit(@{@"state":state});
                }
            }
        }
        dispatch_async(dispatch_get_main_queue(),^{CFRunLoopStop(CFRunLoopGetMain());});
    });
    CFRunLoopRun();worker.join();return result;
}
