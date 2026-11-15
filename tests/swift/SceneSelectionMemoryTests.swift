import Foundation
import CoreGraphics
import simd

@main struct SceneSelectionMemoryTests {
    static func main() {
        let pose=SceneSelectionPose(position:.zero,rotation:SIMD4(0,0,0,1))
        let light=SceneObject(id:"light",name:"Ring light",box:CGRect(x:0.3,y:0.3,width:0.15,height:0.15),contour:[],confidence:0.8)
        let speaker=SceneObject(id:"speaker",name:"Speaker",box:CGRect(x:0.6,y:0.3,width:0.3,height:0.4),contour:[],confidence:0.9)

        var memory=SceneSelectionMemory()
        memory.observe([light,speaker],pose:pose,time:0)
        // A brief failed track/missed detection must not remove the light's
        // button while the user reaches for it. The IDs remain distinct.
        memory.observe([],pose:pose,time:0.2)
        assert(Set(memory.visible(pose:pose,time:0.3).map(\.id)) == ["light","speaker"])
        assert(memory.visible(pose:pose,time:2.8).count == 2)
        assert(memory.visible(pose:pose,time:3.1).isEmpty)

        // Hold the last real geometry while a hand hides the light. It stays
        // selectable throughout pinch-down/release, with one exact device ID.
        memory.observe([light],pose:pose,time:2)
        assert(memory.beginInteraction(pose:pose,time:2.1))
        assert(memory.isHolding(at:4.2))
        assert(memory.visible(pose:pose,time:4.2) == [light])
        var gesture=GestureInteraction()
        let target=GestureTarget(id:"object:light",rect:light.box)
        let point=CGPoint(x:0.35,y:0.35)
        _=gesture.update(point:point,pinched:false,time:2.2,targets:[target])
        _=gesture.update(point:point,pinched:true,time:2.3,targets:[target])
        _=gesture.update(point:point,pinched:true,time:2.7,targets:[])
        _=gesture.update(point:point,pinched:false,time:2.8,targets:[])
        assert(gesture.update(point:point,pinched:false,time:2.9,targets:[])?.target == "object:light")
        assert(gesture.update(point:point,pinched:false,time:3,targets:[]) == nil)

        // Touch-up may precede the button action; keep it until the release
        // finishes, then expire. A second hand appearance cannot revive it.
        memory.endInteraction(time:4.2)
        assert(memory.visible(pose:pose,time:4.3) == [light])
        assert(!memory.beginInteraction(pose:pose,time:4.3))
        assert(memory.visible(pose:pose,time:5.1).isEmpty)

        // A stationary hand cannot keep an old detection forever.
        memory.observe([light],pose:pose,time:10)
        assert(memory.beginInteraction(pose:pose,time:10.1))
        assert(memory.visible(pose:pose,time:12.9) == [light])
        assert(memory.visible(pose:pose,time:13.2).isEmpty)

        // Movement invalidates frozen image coordinates immediately.
        memory.observe([light],pose:pose,time:20)
        assert(memory.beginInteraction(pose:pose,time:20.1))
        let moved=SceneSelectionPose(position:SIMD3(0.2,0,0),rotation:pose.rotation)
        assert(memory.visible(pose:moved,time:20.2).isEmpty)
        assert(!memory.isHolding(at:20.2))
        assert(memory.visible(pose:pose,time:20.3).isEmpty)
        memory.observe([light],pose:pose,time:30)
        assert(memory.beginInteraction(pose:pose,time:30.1))
        let turned=SceneSelectionPose(position:.zero,rotation:simd_quatf(angle:0.6,axis:SIMD3(0,1,0)).vector)
        assert(memory.visible(pose:turned,time:30.2).isEmpty)

        // Closing controls or pausing the camera clears all retained targets.
        memory.observe([light,speaker],pose:pose,time:40)
        memory.clear()
        assert(memory.visible(pose:pose,time:40.1).isEmpty)
        // A drifting local tracker cannot renew a WLED identity indefinitely.
        memory.observe([light],pose:pose,time:50)
        memory.track(light,pose:pose,time:52.5)
        assert(memory.visible(pose:pose,time:53.1).isEmpty)
        // A fresh headphone identity displaces a stale light label at the same
        // location, including when the old light box is smaller than the new box.
        memory.observe([light],pose:pose,time:60)
        let headphones=SceneObject(id:"headphones",name:"Headphones",box:light.box.insetBy(dx:-0.02,dy:-0.02),contour:[],confidence:0.9)
        memory.observe([headphones],pose:pose,time:60.5)
        assert(memory.visible(pose:pose,time:60.6).map(\.id) == ["headphones"])
        print("PASS: light occlusion, pinch identity, touch release, expiry, camera movement and reset")
    }
}
