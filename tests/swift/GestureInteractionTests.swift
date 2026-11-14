import Foundation
import CoreGraphics

@main struct GestureInteractionTests {
    static func main() {
        let target=GestureTarget(id:"device",rect:CGRect(x:0.2,y:0.2,width:0.5,height:0.5))
        let inside=CGPoint(x:0.4,y:0.4)
        var machine=GestureInteraction()
        // Mode entry while already pinching cannot select or send a command.
        assert(machine.update(point:inside,pinched:true,time:0,targets:[target]) == nil)
        assert(machine.started == nil)
        _=machine.update(point:inside,pinched:false,time:0.1,targets:[target])
        _=machine.update(point:inside,pinched:true,time:0.2,targets:[target])
        _=machine.update(point:inside,pinched:true,time:0.6,targets:[target])
        assert(machine.update(point:inside,pinched:false,time:0.7,targets:[target]) == nil)
        assert(machine.update(point:inside,pinched:false,time:0.8,targets:[target])?.target == "device")
        assert(machine.update(point:inside,pinched:false,time:0.9,targets:[target]) == nil)
        // A short pinch is ignored.
        _=machine.update(point:inside,pinched:true,time:1,targets:[target])
        _=machine.update(point:inside,pinched:false,time:1.05,targets:[target])
        assert(machine.update(point:inside,pinched:false,time:1.1,targets:[target]) == nil)
        // Hand loss cancels, even if it was actively pinching.
        _=machine.update(point:inside,pinched:false,time:2,targets:[target])
        _=machine.update(point:inside,pinched:true,time:2.1,targets:[target])
        _=machine.update(point:nil,pinched:false,time:2.5,targets:[target])
        _=machine.update(point:inside,pinched:false,time:2.6,targets:[target])
        assert(machine.update(point:inside,pinched:false,time:2.7,targets:[target]) == nil)
        // Snapshot target survives modest movement; release sends exactly once.
        _=machine.update(point:inside,pinched:true,time:3,targets:[target])
        _=machine.update(point:CGPoint(x:0.8,y:0.2),pinched:true,time:3.4,targets:[])
        _=machine.update(point:inside,pinched:false,time:3.5,targets:[])
        let moved=machine.update(point:inside,pinched:false,time:3.6,targets:[])
        assert(moved?.target == "device")
        assert(abs((moved?.delta ?? 0)-0.2)<0.001)
        assert(machine.update(point:inside,pinched:false,time:3.7,targets:[]) == nil)
        // A long hold times out rather than emitting on release.
        _=machine.update(point:inside,pinched:true,time:4,targets:[target])
        _=machine.update(point:inside,pinched:true,time:17,targets:[target])
        _=machine.update(point:inside,pinched:false,time:17.1,targets:[target])
        assert(machine.update(point:inside,pinched:false,time:17.2,targets:[target]) == nil)
        // Real HUD targets and preview steps share identical geometry/math.
        let hud=GestureHUDLayout.targets(controlIDs:["volume","bass","treble"])
        for id in ["back","close","control:volume","control:bass","control:treble"] {
            assert(hud.contains(where:{$0.id==id}))
        }
        assert(!hud.contains(where:{$0.id=="adjust"}))
        assert(GestureHUDLayout.draggedValue(start:50,delta:0.14,min:0,max:100)==100)
        assert(GestureHUDLayout.draggedValue(start:50,delta:-0.14,min:0,max:100)==0)
        assert(GestureHUDLayout.draggedValue(start:5,delta:0.056,min:0,max:10)==7)
        assert(GestureHUDLayout.draggedValue(start:5,delta:0,min:0,max:10)==5)
        assert(GestureHUDLayout.draggedValue(start:5,delta:.nan,min:0,max:10)==5)
        assert(GestureHUDLayout.fraction(value:200,min:0,max:100)==1)
        let sliders=hud.filter { $0.id.hasPrefix("control:") }
        assert(Set(sliders.map { $0.rect.midY }).count == 1)
        for slider in sliders {
            for fraction in [0.0,0.5,1.0] {
                let thumb=GestureHUDLayout.thumbPoint(in:slider.rect,fraction:fraction)
                let grab=GestureHUDLayout.grabRect(in:slider.rect,fraction:fraction)
                assert(grab.contains(thumb))
                assert(thumb.y>=0.38 && thumb.y<=0.66)
                for other in sliders where other.id != slider.id {
                    assert(!grab.intersects(GestureHUDLayout.grabRect(in:other.rect,fraction:fraction)))
                }
            }
        }
        assert(GestureHUDLayout.thumbPoint(in:sliders[0].rect,fraction:1).y < GestureHUDLayout.thumbPoint(in:sliders[0].rect,fraction:0).y)
        print("PASS: gesture arming, debounce, cancellation, timeout, captured target and vertical slider ranges")
    }
}
