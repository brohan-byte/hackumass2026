#if os(iOS) || os(macOS)
import Foundation
import CoreGraphics
import simd

nonisolated struct SceneObject: Identifiable, Sendable, Equatable {
    let id: String
    let name: String
    var box: CGRect
    var contour: [CGPoint]
    var confidence: Float
}

nonisolated struct SceneSelectionPose: Sendable {
    let position: SIMD3<Float>
    let rotation: SIMD4<Float>

    func isClose(to other: Self) -> Bool {
        simd_distance(position,other.position)<0.10 && abs(simd_dot(rotation,other.rotation))>0.99
    }
}

/// A recent match survives brief occlusion. Interaction freezes that exact
/// identity/geometry for at most three seconds, bounded by camera movement.
nonisolated struct SceneSelectionMemory {
    private struct Entry {
        let object: SceneObject
        let pose: SceneSelectionPose
        let seen: TimeInterval
    }
    private var entries: [String:Entry] = [:]
    private var heldIDs: Set<String> = []
    private var heldUntil: TimeInterval?
    static let grace: TimeInterval = 3
    static let interactionDuration: TimeInterval = 3

    mutating func observe(_ objects: [SceneObject],pose: SceneSelectionPose,time: TimeInterval) {
        // Fresh detector identity overrides an old tracker label at that location.
        entries=entries.filter { id,entry in
            !objects.contains { object in
                guard object.id != id else { return false }
                let intersection=entry.object.box.intersection(object.box)
                guard !intersection.isNull else { return false }
                let area=intersection.width*intersection.height
                let smaller=min(entry.object.box.width*entry.object.box.height,object.box.width*object.box.height)
                return area/max(0.000001,smaller)>0.65
            }
        }
        for object in objects { entries[object.id]=Entry(object:object,pose:pose,seen:time) }
    }

    mutating func track(_ object: SceneObject,pose: SceneSelectionPose,time: TimeInterval) {
        guard let entry=entries[object.id],time-entry.seen<Self.grace else { return }
        // Tracking updates geometry, never the last confirmed recognition time.
        entries[object.id]=Entry(object:object,pose:pose,seen:entry.seen)
    }

    mutating func visible(pose: SceneSelectionPose,time: TimeInterval) -> [SceneObject] {
        entries=entries.filter { id,entry in
            let held=heldIDs.contains(id) && time<(heldUntil ?? -.infinity)
            return entry.pose.isClose(to:pose) && (time-entry.seen<Self.grace || held)
        }
        heldIDs.formIntersection(entries.keys)
        if heldIDs.isEmpty { heldUntil=nil }
        return entries.values.map(\.object).sorted {
            $0.confidence == $1.confidence ? $0.id<$1.id : $0.confidence>$1.confidence
        }
    }

    mutating func beginInteraction(pose: SceneSelectionPose,time: TimeInterval) -> Bool {
        let objects=visible(pose:pose,time:time).filter { time-(entries[$0.id]?.seen ?? -.infinity)<1.5 }
        guard !objects.isEmpty else { return false }
        heldIDs=Set(objects.map(\.id));heldUntil=time+Self.interactionDuration
        return true
    }

    func isHolding(at time: TimeInterval) -> Bool {
        !heldIDs.isEmpty && time<(heldUntil ?? -.infinity)
    }

    mutating func endInteraction(time: TimeInterval) {
        // SwiftUI may deliver touch-up before Button.action. Keep the same
        // target through that release, without extending the original deadline.
        if let deadline=heldUntil,deadline>time { heldUntil=min(deadline,time+0.25) }
        else { heldIDs=[];heldUntil=nil }
    }
    mutating func clear() { entries=[:];heldIDs=[];heldUntil=nil }
}
#endif
