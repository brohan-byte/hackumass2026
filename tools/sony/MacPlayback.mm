#import <Foundation/Foundation.h>
#import <CoreAudio/CoreAudio.h>
#import <AudioToolbox/AudioHardwareService.h>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static void emit(NSDictionary* value) {
    NSData* data=[NSJSONSerialization dataWithJSONObject:value options:0 error:nil];
    std::cout.write((const char*)data.bytes,data.length);std::cout<<std::endl;
}
static void checked(OSStatus status,const char* operation) {
    if(status!=noErr)throw std::runtime_error(std::string(operation)+" failed ("+std::to_string(status)+")");
}
static AudioDeviceID output() {
    AudioDeviceID device=kAudioObjectUnknown;UInt32 size=sizeof(device);
    AudioObjectPropertyAddress property={kAudioHardwarePropertyDefaultOutputDevice,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
    checked(AudioObjectGetPropertyData(kAudioObjectSystemObject,&property,0,nullptr,&size,&device),"Read Mac audio output");
    if(device==kAudioObjectUnknown)throw std::runtime_error("No Mac audio output selected");
    return device;
}
static NSString* text(AudioDeviceID device,AudioObjectPropertySelector selector) {
    CFStringRef value=nullptr;UInt32 size=sizeof(value);
    AudioObjectPropertyAddress property={selector,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
    checked(AudioObjectGetPropertyData(device,&property,0,nullptr,&size,&value),"Read audio identity");
    return CFBridgingRelease(value);
}
static NSArray* outputs() {
    AudioObjectPropertyAddress property={kAudioHardwarePropertyDevices,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
    UInt32 size=0;checked(AudioObjectGetPropertyDataSize(kAudioObjectSystemObject,&property,0,nullptr,&size),"List audio devices");
    std::vector<AudioDeviceID> devices(size/sizeof(AudioDeviceID));
    checked(AudioObjectGetPropertyData(kAudioObjectSystemObject,&property,0,nullptr,&size,devices.data()),"Read audio devices");
    NSMutableArray* result=[NSMutableArray array];
    for(AudioDeviceID device:devices) {
        AudioObjectPropertyAddress streams={kAudioDevicePropertyStreams,kAudioObjectPropertyScopeOutput,kAudioObjectPropertyElementMain};
        UInt32 streamSize=0;
        if(AudioObjectGetPropertyDataSize(device,&streams,0,nullptr,&streamSize)!=noErr || streamSize==0)continue;
        [result addObject:@{@"id":@(device),@"name":text(device,kAudioObjectPropertyName),
            @"uid":text(device,kAudioDevicePropertyDeviceUID),@"selected":@(device==output())}];
    }
    return result;
}
struct Playback {
    AudioDeviceID device;
    NSString* uid;
    NSString* name;
    NSString* model;
    AudioObjectPropertyAddress volume;
    Playback(NSString* expected) {
        device=output();name=text(device,kAudioObjectPropertyName);uid=text(device,kAudioDevicePropertyDeviceUID);
        if([name localizedCaseInsensitiveContainsString:@"WH-1000XM5"])model=@"WH-1000XM5";
        else if([name localizedCaseInsensitiveContainsString:@"WF-1000XM5"])model=@"WF-1000XM5";
        else throw std::runtime_error("Select WH-1000XM5 in Mac System Settings > Sound > Output first. No other output will be changed.");
        if(expected.length && ![expected isEqualToString:uid])throw std::runtime_error("The selected Mac audio output does not match the saved XM5.");
        volume={kAudioHardwareServiceDeviceProperty_VirtualMainVolume,kAudioObjectPropertyScopeOutput,kAudioObjectPropertyElementMain};
        if(!AudioObjectHasProperty(device,&volume))volume.mSelector=kAudioDevicePropertyVolumeScalar;
        Boolean writable=false;
        checked(AudioObjectIsPropertySettable(device,&volume,&writable),"Check Mac playback volume control");
        if(!writable)throw std::runtime_error("The XM5 output does not expose a writable Mac playback volume.");
    }
    void verify() {
        if(output()!=device || ![text(device,kAudioDevicePropertyDeviceUID) isEqualToString:uid])
            throw std::runtime_error("Mac audio output changed. Select the saved XM5 before using its playback controls.");
    }
    int read() {
        verify();Float32 value=0;UInt32 size=sizeof(value);
        checked(AudioObjectGetPropertyData(device,&volume,0,nullptr,&size,&value),"Read XM5 Mac playback volume");
        if(!std::isfinite(value)||value<0||value>1)throw std::runtime_error("Invalid Mac playback volume");
        return (int)std::lround(value*100);
    }
    void set(int value) {
        if(value<0||value>100)throw std::runtime_error("Mac playback volume must be 0–100");
        verify();Float32 scalar=value/100.f;
        checked(AudioObjectSetPropertyData(device,&volume,0,nullptr,sizeof(scalar),&scalar),"Set XM5 Mac playback volume");
    }
};
int main(int argc,const char* argv[]) {
    @autoreleasepool {
        try {
            if(argc>=2 && std::string(argv[1])=="--list") {emit(@{@"outputs":outputs()});return 0;}
            if(argc>=2 && std::string(argv[1])=="--select-xm5") {
                NSMutableArray* matches=[NSMutableArray array];
                for(NSDictionary* item in outputs()) {
                    NSString* name=item[@"name"];
                    if([name localizedCaseInsensitiveContainsString:@"WH-1000XM5"] ||
                       [name localizedCaseInsensitiveContainsString:@"WF-1000XM5"])[matches addObject:item];
                }
                if(matches.count!=1)throw std::runtime_error("Connect exactly one XM5 audio output to the Mac before selecting it.");
                AudioDeviceID device=[matches[0][@"id"] unsignedIntValue];
                AudioObjectPropertyAddress property={kAudioHardwarePropertyDefaultOutputDevice,kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
                checked(AudioObjectSetPropertyData(kAudioObjectSystemObject,&property,0,nullptr,sizeof(device),&device),"Select XM5 playback output");
                emit(@{@"selected":matches[0]});return 0;
            }
            if(argc<2 || (std::string(argv[1])!="--serve" && std::string(argv[1])!="--probe"))
                throw std::runtime_error("Use --probe or --serve [saved audio UID]");
            Playback playback(argc>2?[NSString stringWithUTF8String:argv[2]]:@"");
            int initial=playback.read();
            emit(@{@"address":playback.uid,@"model":playback.model,@"firmware":@"",
                @"controlSource":@"mac-playback",@"deviceName":playback.name,
                @"capabilities":@{@"deviceId":[@"mac-playback:" stringByAppendingString:playback.uid],
                    @"name":@"Sony XM5 · Mac playback",@"controls":@[
                    @{@"id":@"volume",@"label":@"Mac volume",@"type":@"number",@"min":@0,@"max":@100,@"step":@1}]}});
            if(std::string(argv[1])=="--probe") {emit(@{@"state":@{@"volume":@(initial)}});return 0;}
            std::string command;
            while(std::getline(std::cin,command)) {
                if(command=="quit")break;
                try {
                    if(command.rfind("volume ",0)==0) {
                        std::string number=command.substr(7);size_t used=0;int value=std::stoi(number,&used);
                        if(used!=number.size())throw std::runtime_error("Invalid volume command");
                        playback.set(value);
                    } else if(command!="state")throw std::runtime_error("Unknown playback command");
                    emit(@{@"state":@{@"volume":@(playback.read())}});
                } catch(const std::exception& error) {emit(@{@"error":[NSString stringWithUTF8String:error.what()]});}
            }
            return 0;
        } catch(const std::exception& error) {
            emit(@{@"error":[NSString stringWithUTF8String:error.what()]});return 1;
        }
    }
}
