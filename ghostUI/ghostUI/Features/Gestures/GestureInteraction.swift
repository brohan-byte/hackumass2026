#if os(iOS) || os(macOS)
import Foundation
import CoreGraphics

nonisolated struct GestureTarget: Sendable {
    let id: String
    let rect: CGRect
}
nonisolated struct GestureRelease: Sendable {
    let target: String
    let delta: Double
}

/// Pure gesture state machine; snapshots the target at pinch-down so small
/// camera/hand movements do not move the selected target during a gesture.
nonisolated struct GestureInteraction {
    private(set) var target: String?
    private(set) var started: TimeInterval?
    private(set) var delta: Double = 0
    private var originY: CGFloat = 0
    private var releaseFrames = 0
    private var releaseStarted: TimeInterval?
    private var needsOpenHand = true

    mutating func reset() {
        target=nil;started=nil;delta=0;releaseFrames=0;releaseStarted=nil;needsOpenHand=true
    }
    mutating func finishPendingRelease(time: TimeInterval) -> GestureRelease? {
        guard let started,let releaseStarted,let target,
              target.hasPrefix("control:"),time-releaseStarted>=0.12 else { return nil }
        let result = time-started>=0.25 ? GestureRelease(target:target,delta:delta) : nil
        reset()
        return result
    }
    mutating func update(point: CGPoint?, pinched: Bool, time: TimeInterval,
                         targets: [GestureTarget]) -> GestureRelease? {
        guard let point, point.x.isFinite, point.y.isFinite else { reset();return nil }
        if needsOpenHand {
            if !pinched { needsOpenHand=false }
            return nil
        }
        if pinched {
            releaseFrames=0;releaseStarted=nil
            if started == nil {
                target=targets.first(where:{$0.rect.contains(point)})?.id
                started=time;originY=point.y
            }
            delta=Double(originY-point.y)
            if time-(started ?? time)>12 { reset() }
            return nil
        }
        guard let started else { return nil }
        if releaseFrames == 0 { releaseStarted=time }
        releaseFrames += 1
        guard releaseFrames>=2 else { return nil }
        // Brief pinch-ratio flicker must not drop a captured slider mid-drag.
        if target?.hasPrefix("control:") == true { return finishPendingRelease(time:time) }
        let result: GestureRelease? = time-started>=0.25 ? target.map { GestureRelease(target:$0,delta:delta) } : nil
        reset()
        return result
    }
}
nonisolated enum GestureHUDLayout {
    static let railTop = 0.38
    static let railLength = 0.28
    static func targets(controlIDs: [String]) -> [GestureTarget] {
        var targets=[GestureTarget(id:"back",rect:CGRect(x:0.03,y:0.025,width:0.28,height:0.08)),
                     GestureTarget(id:"close",rect:CGRect(x:0.72,y:0.025,width:0.25,height:0.08))]
        let count = min(3, controlIDs.count)
        let startX = 0.5 - (0.22 * Double(count) + 0.04 * Double(max(0,count-1))) / 2
        for (i,id) in controlIDs.prefix(3).enumerated() {
            targets.append(GestureTarget(id:"control:"+id,rect:CGRect(x:startX+Double(i)*0.26,y:0.24,width:0.22,height:0.52)))
        }
        return targets
    }
    static func thumbPoint(in rect: CGRect, fraction: Double) -> CGPoint {
        CGPoint(x:rect.midX,y:railTop+(1-fraction)*railLength)
    }
    static func grabRect(in rect: CGRect, fraction: Double) -> CGRect {
        // Grab anywhere along the rail, then drag relative to the current value.
        // This avoids chasing a thumb near the edge of the camera's hand view.
        return CGRect(x:rect.midX-0.10,y:railTop-0.06,width:0.20,height:railLength+0.12)
    }
    static func fraction(value: Double, min: Double, max: Double) -> Double {
        guard max > min else { return 0 }
        return Swift.max(0,Swift.min(1,(value-min)/(max-min)))
    }
    static func draggedValue(start: Double, delta: Double, min: Double, max: Double) -> Double {
        guard delta.isFinite else { return start }
        return Swift.max(min,Swift.min(max,(start+delta/railLength*(max-min)).rounded()))
    }
}
#endif
