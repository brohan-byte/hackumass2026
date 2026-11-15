import Foundation

@main struct ControlLayoutTests {
    static func main() throws {
        let caps = DeviceCapabilities(deviceId:"speaker-1",name:"Speaker",simulated:true,controls:[
            DeviceControl(id:"volume",label:"Volume",min:0,max:31,step:1),
            DeviceControl(id:"bass",label:"Bass",min:0,max:10,step:1)])
        let layout = ControlLayout(title:"Sound",controls:[
            .init(bind:"bass",label:"Low end",widget:"slider",group:"Tone"),
            .init(bind:"volume",label:"Loudness",widget:"slider",group:"Sound")])
        let response = ControlLayoutResponse(deviceId:"speaker-1",layout:layout,source:"ai",notice:"Saved",cached:true)
        try response.validate(for:caps)
        let wrong = ControlLayoutResponse(deviceId:"other-device",layout:layout,source:"ai",notice:"Saved",cached:true)
        do { try wrong.validate(for:caps); fatalError("Accepted another device's layout") }
        catch { }
        let resolved = try layout.resolvedControls(caps)
        assert(resolved.map(\.id) == ["bass","volume"])
        assert(resolved[0].label == "Low end" && resolved[1].max == 31)
        assert(resolved[0].min == 0 && resolved[0].max == 10 && resolved[0].step == 1)
        for bad in [
            ControlLayout(title:"Bad",controls:[layout.controls[0],layout.controls[0]]),
            ControlLayout(title:"Bad",controls:[.init(bind:"power",label:"Power",widget:"slider",group:"A"),layout.controls[0]]),
            ControlLayout(title:"Bad",controls:[.init(bind:"volume",label:"Volume",widget:"script",group:"A"),layout.controls[0]])] {
            do { _ = try bad.resolvedControls(caps); fatalError("Accepted invalid layout") }
            catch { }
        }
        let fallback = try ControlLayout.fallback(caps).resolvedControls(caps)
        assert(fallback.count == 2)
        print("PASS: native layout ordering, labels, binding rejection and capability range preservation")
    }
}
