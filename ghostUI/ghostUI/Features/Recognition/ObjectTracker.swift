#if os(iOS)
import ARKit
import Vision
import Combine
import UIKit

/// Periodic local-Mac YOLOE detections + fast iPhone Vision tracking.
@MainActor final class ObjectTracker: ObservableObject {
    @Published private(set) var sceneObjects: [SceneObject] = []
    private var sceneWorkers: [String:RegionTrackingWorker] = [:]
    private var sceneSeeds: [String:CGRect] = [:]
    private var sceneBusy: Set<String> = []
    private var sceneMemory=SceneSelectionMemory()
    private var selectionInteraction=false
    private var interactionHeld=false
    @Published private(set) var box: CGRect?
    @Published private(set) var contour: [CGPoint] = []
    private var contourReferenceBox: CGRect?
    @Published private(set) var message = "Loading local detector status…"
    @Published private(set) var confidence: Float = 0
    @Published private(set) var views = 0
    @Published private(set) var enrolling = false
    @Published private(set) var ready = false
    var client: RecognitionClient?
    private var latestSnapshot: (() -> UIImage)?
    private var frame: ARFrame?
    private var display = CGAffineTransform.identity
    private var seed: CGRect?
    private var enrollmentJPEG: Data?
    @Published private(set) var enrollmentPreview: UIImage?
    private var generation = UUID()
    private var trackingBusy = false
    private var detectionBusy = false
    private var lastTrack: TimeInterval = 0
    private var lastDetect = Date.distantPast
    private var enabled = true
    private var detectedOrientation: UIInterfaceOrientation?
    private let worker = RegionTrackingWorker()

    func configure(_ client: RecognitionClient) async {
        reset()
        ready=false; views=0
        self.client = client
        do {
            let status = try await client.status()
            views = status.views; ready = status.modelAvailable
            message = !ready ? "Object recognition needs setup on your Mac." : views == 0 ? "Register an object to get started." : "Point at a registered object."
        } catch { message = error.localizedDescription }
    }
    func clearEnrollment() async {
        guard !detectionBusy, !enrolling, let client else { return }
        generation = UUID(); box = nil; seed = nil
        do { let state = try await client.clear(); views = state.views; message = "Enrollment cleared. Draw the first view." }
        catch { message = error.localizedDescription }
    }
    func stageEnrollmentImage() {
        enrollmentJPEG = nil
        enrollmentPreview = nil
        guard let image = latestSnapshot?(), image.size.width > 0, image.size.height > 0 else {
            message = "Camera frame unavailable. Wait for the live view, then draw again."
            return
        }
        enrollmentJPEG = jpegSnapshot(image)
        if enrollmentJPEG != nil { enrollmentPreview = image }
        else { message = "Could not capture this view. Draw again." }
    }
    func discardEnrollmentImage() {
        enrollmentJPEG = nil
        enrollmentPreview = nil
    }
    func select(_ rect: CGRect) async -> Bool {
        guard !enrolling else { return false }
        guard !detectionBusy else {
            message = "Waiting for the previous detection. Retry saving shortly."
            return false
        }
        guard let client else {
            message = "Device connection unavailable. Close AR and reconnect."
            return false
        }
        guard let jpeg = enrollmentJPEG else {
            message = "No camera image captured. Draw a new box over the live view."
            return false
        }
        enrolling = true; generation = UUID(); box = nil; seed = nil
        defer { enrolling = false }
        message = "Saving boxed view on your Mac…"
        print("GhostUI enrollment: sending JPEG (\(jpeg.count) bytes), box \(rect)")
        do {
            let result = try await client.enroll(jpeg,box:rect)
            views = result.views
            discardEnrollmentImage()
            message = "Saved view \(views)/4. Detection resumes automatically. Use Add view for another angle."
            lastDetect = .distantPast
            return true
        } catch {
            message = "Enrollment failed: " + error.localizedDescription
            print("GhostUI enrollment failed: \(error.localizedDescription)")
            return false
        }
    }
    func reset(_ reason: String = "Finding enrolled object again…") {
        sceneObjects=[];sceneSeeds=[:];sceneWorkers=[:];sceneBusy=[]
        sceneMemory.clear();selectionInteraction=false;interactionHeld=false
        generation = UUID(); box = nil; seed = nil; contour = []; contourReferenceBox = nil; confidence = 0; lastTrack = 0
        message = reason
    }
    func pause(_ paused: Bool) {
        enabled = !paused
        if paused {
            generation = UUID();box=nil;seed=nil;sceneObjects=[];sceneSeeds=[:];sceneBusy=[]
            sceneMemory.clear();selectionInteraction=false;interactionHeld=false
        }
    }
    private var scenePose: SceneSelectionPose? {
        guard let matrix=frame?.camera.transform else { return nil }
        return SceneSelectionPose(position:SIMD3(matrix.columns.3.x,matrix.columns.3.y,matrix.columns.3.z),
                                  rotation:simd_quatf(matrix).vector)
    }
    private var selectionTime: TimeInterval { ProcessInfo.processInfo.systemUptime }

    func setSelectionInteraction(_ active: Bool) {
        guard enabled,client?.isScene == true else { return }
        if active != selectionInteraction {
            selectionInteraction=active
            if !active {
                sceneMemory.endInteraction(time:selectionTime);interactionHeld=false;lastDetect = .distantPast
            }
        }
        refreshSceneSelection()
    }

    func canSelectSceneObject(_ id: String) -> Bool {
        refreshSceneSelection()
        return enabled && sceneObjects.contains(where:{$0.id==id})
    }

    private func refreshSceneSelection() {
        guard let pose=scenePose else { return }
        let now=selectionTime
        let visible=sceneMemory.visible(pose:pose,time:now)
        if visible != sceneObjects {
            sceneObjects=visible
            let ids=Set(visible.map(\.id))
            sceneWorkers=sceneWorkers.filter{ids.contains($0.key)}
            sceneSeeds=sceneSeeds.filter{ids.contains($0.key)}
        }
        if selectionInteraction && !interactionHeld && sceneMemory.beginInteraction(pose:pose,time:now) {
            interactionHeld=true
            // Discard object results captured before the hand entered the view.
            generation=UUID();sceneBusy=[]
            sceneSeeds=Dictionary(uniqueKeysWithValues:visible.map{($0.id,$0.box)})
        }
    }

    private func jpegSnapshot() -> Data? {
        guard let image = latestSnapshot?() else { return nil }
        return jpegSnapshot(image)
    }
    private func jpegSnapshot(_ image: UIImage) -> Data? {
        guard image.size.width > 0, image.size.height > 0 else { return nil }
        let scale = min(1, 960/max(image.size.width,image.size.height))
        let size = CGSize(width:image.size.width*scale,height:image.size.height*scale)
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        return UIGraphicsImageRenderer(size:size,format:format).image { _ in
            image.draw(in:CGRect(origin:.zero,size:size))
        }.jpegData(compressionQuality:0.7)
    }
    func process(_ frame: ARFrame, orientation: UIInterfaceOrientation, viewport: CGSize,
                 snapshot: @escaping () -> UIImage) {
        self.frame = frame; latestSnapshot = snapshot
        display = frame.displayTransform(for:orientation,viewportSize:viewport)
        if detectedOrientation != orientation {
            detectedOrientation = orientation; reset("Orientation changed. Looking for the enrolled object…")
        }
        guard enabled, !enrolling else { return }
        if client?.isScene == true {
            refreshSceneSelection()
            if sceneMemory.isHolding(at:selectionTime) { return }
        }
        // Single request in flight; no queue of stale frames. Detector retries
        // periodically even when tracking succeeds, correcting local drift.
        let detectionInterval: TimeInterval = sceneObjects.isEmpty && box == nil ? 0.8 : 1.5
        if ready, views>0, !detectionBusy, Date().timeIntervalSince(lastDetect)>detectionInterval,
           let client, let jpeg=jpegSnapshot() {
            detectionBusy = true; lastDetect = Date()
            let id = generation, capturePose = frame.camera.transform
            let start = Date()
            if box == nil { message = "Looking for registered objects…" }
            Task {
                defer { detectionBusy = false; lastDetect = Date() }
                do {
                    let result = try await client.detect(jpeg)
                    guard enabled, generation == id else { return }
                    guard let current=self.frame else { return }
                    let oldPosition=SIMD3<Float>(capturePose.columns.3.x,capturePose.columns.3.y,capturePose.columns.3.z)
                    let newPosition=SIMD3<Float>(current.camera.transform.columns.3.x,current.camera.transform.columns.3.y,current.camera.transform.columns.3.z)
                    let rotation=abs(simd_dot(simd_quatf(capturePose).vector,simd_quatf(current.camera.transform).vector))
                    // Old image coordinates cannot be pasted onto a moved camera.
                    guard simd_distance(oldPosition,newPosition)<0.10, rotation>0.99,
                          Date().timeIntervalSince(start)<12 else {
                        message = "Hold steady for another moment."; return
                    }
                    if client.isScene {
                        installScene(result)
                        return
                    }
                    let matches=result.detections.filter { $0.score>=0.35 && $0.box.count==4 }
                    guard matches.count == 1, let detected=matches.first else {
                        reset(matches.isEmpty ? "No match. Show an enrolled side, or add another reference view." : "Several matches. Frame only the intended device before continuing.")
                        return
                    }
                    let b=detected.box
                    let rect=CGRect(x:b[0],y:b[1],width:b[2],height:b[3])
                    guard rect.width>0.01,rect.height>0.01,rect.minX>=0,rect.minY>=0,rect.maxX<=1.001,rect.maxY<=1.001 else { return }
                    generation=UUID();seed=rect;box=rect;confidence=Float(detected.score)
                    contour=(detected.polygon ?? []).compactMap { point in
                        guard point.count==2,point.allSatisfy({ $0.isFinite && $0>=0 && $0<=1 }) else { return nil }
                        return CGPoint(x:point[0],y:point[1])
                    }
                    contourReferenceBox=rect
                    message="YOLOE detected object · tap highlight. Mac inference: \(result.latencyMs) ms."
                } catch { if generation == id { message = error.localizedDescription } }
            }
        }
        if client?.isScene == true {
            trackScene(frame)
            return
        }
        guard box != nil, !trackingBusy, frame.timestamp-lastTrack>0.10 else { return }
        trackingBusy=true;lastTrack=frame.timestamp
        let id=generation,initial=seed;seed=nil
        worker.track(frame.capturedImage,generation:id,seed:initial,display:display) { [weak self] result in
            guard let self else { return }
            Task { @MainActor in
                self.trackingBusy=false
                guard self.generation==id else { return }
                if let (box,score)=result, score>=0.45 {
                    if let previous=self.contourReferenceBox,previous.width>0,previous.height>0 {
                        // Between detector masks this is an approximate contour warp,
                        // not fresh pixel segmentation on every camera frame.
                        self.contour=self.contour.map { point in CGPoint(
                            x:box.minX+(point.x-previous.minX)*box.width/previous.width,
                            y:box.minY+(point.y-previous.minY)*box.height/previous.height) }
                        self.contourReferenceBox=box
                    }
                    self.box=box;self.confidence=score
                }
                else { self.reset("Tracking lost. YOLOE will search again; hold steady.") }
            }
        }
    }
    private func installScene(_ result: RecognitionResult) {
        var found: [SceneObject] = []
        for detection in result.detections {
            guard let id=detection.deviceId,let name=detection.name,detection.score>=0.35,
                  detection.box.count==4,detection.box.allSatisfy({$0.isFinite}) else { continue }
            let b=detection.box, rect=CGRect(x:b[0],y:b[1],width:b[2],height:b[3])
            guard rect.width>0.01,rect.height>0.01,rect.minX>=0,rect.minY>=0,
                  rect.maxX<=1.001,rect.maxY<=1.001,!found.contains(where:{$0.id==id}) else { continue }
            let contour=(detection.polygon ?? []).compactMap { point -> CGPoint? in
                guard point.count==2,point.allSatisfy({$0.isFinite && $0>=0 && $0<=1}) else { return nil }
                return CGPoint(x:point[0],y:point[1])
            }
            found.append(SceneObject(id:id,name:name,box:rect,contour:contour,confidence:Float(detection.score)))
        }
        guard let pose=scenePose else { return }
        sceneMemory.observe(found,pose:pose,time:selectionTime)
        let visible=sceneMemory.visible(pose:pose,time:selectionTime)
        generation=UUID();sceneObjects=visible;sceneBusy=[]
        sceneSeeds=Dictionary(uniqueKeysWithValues:visible.map{($0.id,$0.box)})
        sceneWorkers=sceneWorkers.filter { key,_ in visible.contains(where:{$0.id==key}) }
        refreshSceneSelection()
        message=visible.isEmpty ? "Point at a registered object, or register a new one." : "Tap an outline or point and pinch."
    }

    private func trackScene(_ frame: ARFrame) {
        guard !sceneObjects.isEmpty,frame.timestamp-lastTrack>0.10 else { return }
        lastTrack=frame.timestamp
        for object in sceneObjects where !sceneBusy.contains(object.id) {
            let worker=sceneWorkers[object.id] ?? RegionTrackingWorker()
            sceneWorkers[object.id]=worker;sceneBusy.insert(object.id)
            let generationID=generation,seed=sceneSeeds.removeValue(forKey:object.id)
            worker.track(frame.capturedImage,generation:generationID,seed:seed,display:display) { [weak self] result in
                guard let self else { return }
                Task { @MainActor in
                    guard self.generation==generationID else { return }
                    self.sceneBusy.remove(object.id)
                    guard let index=self.sceneObjects.firstIndex(where:{$0.id==object.id}) else { return }
                    guard let (box,score)=result,score>=0.45 else {
                        // Keep the recent hit target briefly while the hand
                        // covers the object; reseed local tracking on retry.
                        self.sceneWorkers.removeValue(forKey:object.id)
                        self.sceneSeeds[object.id]=self.sceneObjects[index].box
                        self.refreshSceneSelection()
                        return
                    }
                    let previous=self.sceneObjects[index].box
                    var updated=self.sceneObjects[index]
                    updated.contour=updated.contour.map { point in CGPoint(
                        x:box.minX+(point.x-previous.minX)*box.width/previous.width,
                        y:box.minY+(point.y-previous.minY)*box.height/previous.height) }
                    updated.box=box;updated.confidence=score
                    if let pose=self.scenePose {
                        self.sceneMemory.track(updated,pose:pose,time:self.selectionTime)
                        self.refreshSceneSelection()
                    }
                }
            }
        }
    }

}

private final class RegionTrackingWorker: @unchecked Sendable {
    private let queue=DispatchQueue(label:"ghostui.vision.local")
    private var generation:UUID?
    private var observation:VNDetectedObjectObservation?
    private var handler=VNSequenceRequestHandler()
    func track(_ pixels:CVPixelBuffer,generation:UUID,seed:CGRect?,display:CGAffineTransform,
               completion:@escaping @Sendable ((CGRect,Float)?)->Void) {
        queue.async { [self] in
            if self.generation != generation {
                self.generation=generation;handler=VNSequenceRequestHandler();observation=nil
                if let seed {
                    let top=seed.applying(display.inverted()).standardized
                    observation=VNDetectedObjectObservation(boundingBox:CGRect(x:top.minX,y:1-top.maxY,width:top.width,height:top.height))
                }
            }
            guard let observation else { completion(nil);return }
            do {
                let request=VNTrackObjectRequest(detectedObjectObservation:observation);request.trackingLevel = .accurate
                try handler.perform([request],on:pixels,orientation:.up)
                guard let next=request.results?.first as? VNDetectedObjectObservation else { completion(nil);return }
                self.observation=next
                let b=next.boundingBox
                let screen=CGRect(x:b.minX,y:1-b.maxY,width:b.width,height:b.height).applying(display).standardized.intersection(CGRect(x:0,y:0,width:1,height:1))
                completion(screen.isNull ? nil : (screen,next.confidence))
            }catch{completion(nil)}
        }
    }
}
#endif
