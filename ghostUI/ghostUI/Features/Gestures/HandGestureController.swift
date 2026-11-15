#if os(iOS)
import ARKit
import Vision
import Combine
import UIKit

@MainActor final class HandGestureController: ObservableObject {
    enum Mode { case off, deviceSelection, hud }
    @Published private(set) var message = "Point at an outlined object, pinch, then release."
    @Published private(set) var landmarks: [CGPoint] = []
    @Published private(set) var cursor: CGPoint?
    @Published private(set) var previewDelta: Double = 0
    @Published private(set) var pinchActive = false
    @Published private(set) var selectedControlID: String?
    @Published private(set) var previewValue: Double?
    private var sliderControls: [DeviceControl] = []
    private var sliderValues: [String:Double] = [:]
    private var dragStart: Double?
    private var filteredCursor: CGPoint?
    func configureSliders(_ controls: [DeviceControl], values: [String:Double]) {
        sliderControls=controls;sliderValues=values
    }
    @Published private(set) var hoveredTarget: String?
    var onSelectDevice: (() -> Void)?
    var onSelectObject: ((String) -> Void)?
    private var sceneTargets: [GestureTarget] = []
    var onBack: (() -> Void)?
    var onClose: (() -> Void)?
    var onCommit: ((String, Int) -> Void)?
    private var mode: Mode = .off
    private var controlIDs: [String] = []
    private var commandBusy = false
    private var awaitingConfirmation = false
    private var working = false
    private var generation = UUID()
    private var lastFrame: TimeInterval = 0
    private var lastUsableFrame: TimeInterval = -.infinity
    private var machine = GestureInteraction()
    private var deviceBox: CGRect?
    private var deviceBoxSeen = Date.distantPast
    private let worker = HandPoseWorker()

    var isHUD: Bool { mode == .hud }
    func setMode(_ value: Mode, controls: [String] = []) {
        awaitingConfirmation=false
        mode=value;controlIDs=Array(controls.prefix(3));generation=UUID();machine.reset()
        previewValue=nil;dragStart=nil;filteredCursor=nil;previewDelta=0;pinchActive=false;hoveredTarget=nil
        if value == .hud { selectedControlID=controlIDs.first }
        if value == .deviceSelection { sceneTargets=[];deviceBox=nil;deviceBoxSeen = .distantPast }
        if value == .off { landmarks=[];cursor=nil }
        message=value == .hud ? "Pinch anywhere on a slider rail, drag up or down, then release to apply." : "Point index at highlighted object. Pinch and release to open controls."
    }
    func cancelGesture() {
        awaitingConfirmation=false
        generation=UUID();machine.reset();previewValue=nil;dragStart=nil;filteredCursor=nil;previewDelta=0;pinchActive=false
        message="Gesture cancelled. Open your hand before starting again."
    }
    func setCommandBusy(_ value: Bool) {
        commandBusy=value
        if value {
            generation=UUID();machine.reset();dragStart=nil;filteredCursor=nil;previewDelta=0;pinchActive=false
            if !awaitingConfirmation { previewValue=nil }
        } else if awaitingConfirmation {
            awaitingConfirmation=false;previewValue=nil
        }
    }
    private func applyRelease(_ event: GestureRelease) {
        switch event.target {
        case "device": onSelectDevice?()
        case "back": onBack?()
        case "close": onClose?()
        default:
            if event.target.hasPrefix("object:") {
                onSelectObject?(String(event.target.dropFirst(7)))
            } else if event.target.hasPrefix("control:"),let start=dragStart,
                      let control=sliderControls.first(where:{"control:"+$0.id==event.target}) {
                let value=GestureHUDLayout.draggedValue(start:start,delta:event.delta,min:control.min,max:control.max)
                if value != start {
                    selectedControlID=control.id;previewValue=value;awaitingConfirmation=true
                    message="Sending slider value…";onCommit?(control.id,Int(value))
                }
            }
        }
        dragStart=nil
        if !awaitingConfirmation { previewValue=nil }
    }
    func setDeviceBox(_ box: CGRect?) {
        if let box { deviceBox=box;deviceBoxSeen=Date() }
    }
    func setDeviceObjects(_ objects: [SceneObject]) {
        sceneTargets=objects.map { GestureTarget(id:"object:"+$0.id,rect:$0.box.insetBy(dx:-0.025,dy:-0.025)) }
    }
    private func targets() -> [GestureTarget] {
        if mode == .hud { return GestureHUDLayout.targets(controlIDs:controlIDs).map { target in
            guard target.id.hasPrefix("control:"),let c=sliderControls.first(where:{ "control:"+$0.id == target.id }) else { return target }
            let fraction=GestureHUDLayout.fraction(value:sliderValues[c.id] ?? c.min,min:c.min,max:c.max)
            return GestureTarget(id:target.id,rect:GestureHUDLayout.grabRect(in:target.rect,fraction:fraction))
        } }
        if mode == .deviceSelection,!sceneTargets.isEmpty { return sceneTargets }
        if mode == .deviceSelection,let box=deviceBox,Date().timeIntervalSince(deviceBoxSeen)<1.5 {
            return [GestureTarget(id:"device",rect:box.insetBy(dx:-0.035,dy:-0.025))]
        }
        return []
    }
    func process(_ frame: ARFrame,orientation:UIInterfaceOrientation,viewport:CGSize) {
        guard mode != .off,!working,frame.timestamp-lastFrame>0.05 else { return }
        working=true;lastFrame=frame.timestamp
        let id=generation,time=frame.timestamp
        let transform=frame.displayTransform(for:orientation,viewportSize:viewport)
        worker.detect(frame.capturedImage,display:transform) { [weak self] pose in
            guard let self else { return }
            Task { @MainActor in
                self.working=false
                guard self.mode != .off,self.generation==id else { return }
                guard let pose else {
                    if !self.commandBusy,let release=self.machine.finishPendingRelease(time:time) {
                        self.applyRelease(release);return
                    }
                    if self.machine.started != nil,time-self.lastUsableFrame<0.35 {
                        self.message="Keep pinching; recovering hand tracking…";return
                    }
                    self.machine.reset();self.previewValue=nil;self.dragStart=nil;self.filteredCursor=nil;self.landmarks=[];self.cursor=nil
                    self.previewDelta=0;self.pinchActive=false;self.hoveredTarget=nil
                    self.message="Show one clear hand to the REAR camera. Gesture cancelled if the hand is lost.";return
                }
                self.landmarks=pose.points
                let old=self.filteredCursor ?? pose.cursor
                let point=CGPoint(x:old.x+0.55*(pose.cursor.x-old.x),y:old.y+0.55*(pose.cursor.y-old.y))
                self.filteredCursor=point;self.cursor=point
                guard pose.usable,!self.commandBusy else {
                    if !self.commandBusy,let release=self.machine.finishPendingRelease(time:time) {
                        self.applyRelease(release);return
                    }
                    if !self.commandBusy,self.machine.started != nil,time-self.lastUsableFrame<0.35 {
                        self.message="Keep pinching; recovering fingertips…";return
                    }
                    self.machine.reset();self.previewValue=nil;self.dragStart=nil;self.filteredCursor=nil;self.previewDelta=0;self.pinchActive=false
                    self.message=self.commandBusy ? "Waiting for device confirmation…" : "Hand seen, but fingertips are unclear. Face your palm toward the camera.";return
                }
                self.lastUsableFrame=time
                let targets=self.targets()
                self.hoveredTarget=targets.first(where:{$0.rect.contains(point)})?.id
                let pinched=pose.ratio < (self.machine.started == nil ? 0.36 : 0.50)
                let previousStart=self.machine.started
                let event=self.machine.update(point:point,pinched:pinched,time:time,targets:targets)
                self.pinchActive=self.machine.started.map { time-$0>=0.25 } ?? false
                if previousStart == nil, let target=self.machine.target, target.hasPrefix("control:") {
                    let controlID=String(target.dropFirst(8))
                    self.selectedControlID=controlID
                    self.dragStart=self.sliderValues[controlID] ?? self.sliderControls.first(where:{$0.id==controlID})?.min
                }
                if let controlID=self.selectedControlID,let start=self.dragStart,
                   let c=self.sliderControls.first(where:{$0.id==controlID}),self.machine.started != nil {
                    self.previewValue=GestureHUDLayout.draggedValue(start:start,delta:self.machine.delta,min:c.min,max:c.max)
                }

                if self.machine.started == nil && event == nil && !self.awaitingConfirmation { self.previewValue=nil;self.dragStart=nil }
                if let event {
                    self.applyRelease(event)
                } else if self.machine.target?.hasPrefix("control:") == true {
                    self.message="Drag up / down. Release to apply; hide hand to cancel."

                } else if self.hoveredTarget != nil {
                    self.message=self.pinchActive ? "Release to select." : "Target highlighted. Pinch briefly and release."
                } else { self.message=self.mode == .hud ? "Pinch anywhere on a slider rail, then drag up or down." : "Point index at the object outline, pinch, then release." }
            }
        }
    }
}
nonisolated private struct HandFramePixels: @unchecked Sendable { let buffer: CVPixelBuffer }
nonisolated private struct HandPose: Sendable {
    let ratio:CGFloat
    let y:CGFloat
    let points:[CGPoint]
    let cursor:CGPoint
    let usable:Bool
}
nonisolated private final class HandPoseWorker: @unchecked Sendable {
    private let queue=DispatchQueue(label:"ghostui.handpose",qos:.userInitiated)
    func detect(_ pixels:CVPixelBuffer,display:CGAffineTransform,completion:@escaping @Sendable (HandPose?)->Void) {
        // AR camera buffers are retained and read-only on this worker.
        let frame = HandFramePixels(buffer:pixels)
        queue.async {
            do {
                let request=VNDetectHumanHandPoseRequest();request.maximumHandCount=2
                try VNImageRequestHandler(cvPixelBuffer:frame.buffer,orientation:.up).perform([request])
                guard let results=request.results,results.count==1,let hand=results.first else { completion(nil);return }
                let thumb=try hand.recognizedPoint(.thumbTip),index=try hand.recognizedPoint(.indexTip)
                let left=try hand.recognizedPoint(.indexMCP),right=try hand.recognizedPoint(.littleMCP)
                let recognized=try hand.recognizedPoints(.all)
                let points=recognized.values.filter { $0.confidence>0.3 }.map {
                    CGPoint(x:$0.location.x,y:1-$0.location.y).applying(display)
                }
                let usable=thumb.confidence>0.35 && index.confidence>0.35 && left.confidence>0.25 && right.confidence>0.25
                let width=hypot(left.location.x-right.location.x,left.location.y-right.location.y)
                
                let distance=hypot(thumb.location.x-index.location.x,thumb.location.y-index.location.y)
                let point=CGPoint(x:index.location.x,y:1-index.location.y).applying(display)
                completion(HandPose(ratio:width>0.02 ? distance/width : 10,y:point.y,points:points,cursor:point,usable:usable && width>0.02))
            }catch{completion(nil)}
        }
    }
}
#endif
