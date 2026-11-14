#if os(iOS)
import ARKit
import Vision
import Combine
import UIKit

/// Periodic local-Mac YOLOE detections + fast iPhone Vision tracking.
@MainActor final class ObjectTracker: ObservableObject {
    @Published private(set) var box: CGRect?
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
    private var generation = UUID()
    private var trackingBusy = false
    private var detectionBusy = false
    private var lastTrack: TimeInterval = 0
    private var lastDetect = Date.distantPast
    private var enabled = true
    private var detectedOrientation: UIInterfaceOrientation?
    private let worker = RegionTrackingWorker()

    func configure(_ client: RecognitionClient) async {
        self.client = client
        do {
            let status = try await client.status()
            views = status.views; ready = status.modelAvailable
            message = !ready ? "Model missing on Mac. Run tools/setup_vision.py." : views == 0 ? "Enroll up to four boxed views: front, left, right, and another distance." : "Saved views loaded. Hold steady while YOLOE searches."
        } catch { message = error.localizedDescription }
    }
    func clearEnrollment() async {
        guard !detectionBusy, !enrolling, let client else { return }
        generation = UUID(); box = nil; seed = nil
        do { let state = try await client.clear(); views = state.views; message = "Enrollment cleared. Draw the first view." }
        catch { message = error.localizedDescription }
    }
    func stageEnrollmentImage() {
        enrollmentJPEG = jpegSnapshot()
    }
    func select(_ rect: CGRect) {
        guard !enrolling, !detectionBusy, let client, let jpeg = enrollmentJPEG ?? jpegSnapshot() else {
            message = "Wait for vision to finish and the camera to be ready."; return
        }
        enrolling = true; generation = UUID(); box = nil; seed = nil
        message = "Saving boxed view on your Mac…"
        print("GhostUI enrollment: sending JPEG (\(jpeg.count) bytes)")
        Task {
            defer { enrolling = false }
            do {
                let result = try await client.enroll(jpeg,box:rect)
                views = result.views
                enrollmentJPEG = nil
                message = "Saved view \(views)/4. Add another angle, or tap Start detection."
                lastDetect = .distantPast
            } catch {
                message = "Enrollment failed: " + error.localizedDescription
                print("GhostUI enrollment failed: \(error.localizedDescription)")
            }
        }
    }
    func reset(_ reason: String = "Finding enrolled object again…") {
        generation = UUID(); box = nil; seed = nil; confidence = 0; lastTrack = 0
        message = reason
    }
    func pause(_ paused: Bool) {
        enabled = !paused
        if paused { generation = UUID(); box = nil; seed = nil }
    }
    private func jpegSnapshot() -> Data? {
        guard let image = latestSnapshot?(), image.size.width > 0 else { return nil }
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
        // Single request in flight; no queue of stale frames. Detector retries
        // periodically even when tracking succeeds, correcting local drift.
        if ready, views>0, !detectionBusy, Date().timeIntervalSince(lastDetect)>3,
           let client, let jpeg=jpegSnapshot() {
            detectionBusy = true; lastDetect = Date()
            let id = generation, capturePose = frame.camera.transform
            let start = Date()
            if box == nil { message = "YOLOE searching on Mac… Hold the phone steady." }
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
                        message = result.latencyMs > 10000 ? "Model finished warming up. Hold steady for the next detection." : "Detection arrived after camera movement. Hold steady for another search."; return
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
                    message="YOLOE detected object · tap highlight. Mac inference: \(result.latencyMs) ms."
                } catch { if generation == id { message = error.localizedDescription } }
            }
        }
        guard box != nil, !trackingBusy, frame.timestamp-lastTrack>0.10 else { return }
        trackingBusy=true;lastTrack=frame.timestamp
        let id=generation,initial=seed;seed=nil
        worker.track(frame.capturedImage,generation:id,seed:initial,display:display) { [weak self] result in
            Task { @MainActor in
                guard let self else { return };self.trackingBusy=false
                guard self.generation==id else { return }
                if let (box,score)=result, score>=0.45 { self.box=box;self.confidence=score }
                else { self.reset("Tracking lost. YOLOE will search again; hold steady.") }
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
