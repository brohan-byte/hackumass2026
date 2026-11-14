import SwiftUI
#if os(iOS)
import ARKit
import SceneKit
import AVFoundation
import UIKit

struct ARScreen<Controls: View>: View {
    let deviceName: String
    let recognition: RecognitionClient
    @ViewBuilder var controls: () -> Controls
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var tracker = ObjectTracker()
    @State private var permission = false
    @State private var selecting = true
    @State private var pendingBox: CGRect?
    @State private var drawingMessage = "Drag below this panel to select the device."
    @State private var showingControls = false
    @State private var diagnostics = "Waiting for camera"

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .top) {
                Color.black
                if permission && ARWorldTrackingConfiguration.isSupported {
                    TrackingCameraView(tracker: tracker, diagnostics: $diagnostics)
                        .frame(width: geometry.size.width, height: geometry.size.height)
                    ObjectSelectionOverlay(box: selecting ? pendingBox : tracker.box, selecting: selecting,
                        deviceName: deviceName,
                        onRegister: { rect in tracker.stageEnrollmentImage(); pendingBox = rect; drawingMessage = "Box selected. Tap Save view to enroll it." },
                        onSelect: { guard !showingControls else { return }; showingControls = true },
                        onInvalid: { drawingMessage = "Box too small. Drag a box at least 44 points wide and tall." })
                        .allowsHitTesting(!showingControls)
                }
                VStack(spacing: 8) {
                    HStack {
                        Button("Close") { dismiss() }
                        Spacer()
                        Button("Add view") { tracker.reset(); pendingBox = nil; selecting = true }
                            .disabled(!permission || tracker.enrolling || tracker.views >= 4)
                    }
                    HStack {
                        Text("Enrolled views: \(tracker.views)/4").font(.caption)
                        Spacer()
                        Button("Start detection") { pendingBox = nil; selecting = false; tracker.pause(false) }
                            .disabled(tracker.views == 0 || tracker.enrolling || !tracker.ready)
                        Button("Clear") { Task { await tracker.clearEnrollment(); pendingBox = nil; selecting = true } }
                            .disabled(tracker.enrolling)
                    }
                    if selecting {
                        HStack {
                            Button(tracker.enrolling ? "Saving…" : "Save view") {
                                if let pendingBox { tracker.select(pendingBox) }
                            }.buttonStyle(.borderedProminent)
                                .disabled(pendingBox == nil || tracker.enrolling)
                            Text(drawingMessage).font(.caption)
                        }
                    }
                    Text(tracker.message).font(.callout).multilineTextAlignment(.center)
                    Text("YOLOE runs on your Mac. Boxed references are saved locally; live frames stay in memory. No images go to Gemini.")
                        .font(.caption).multilineTextAlignment(.center)
                    Text(diagnostics).font(.caption.monospaced()).foregroundStyle(.secondary)
                    Button("Open controls") { showingControls = true }.buttonStyle(.bordered)
                }
                .padding().background(.ultraThinMaterial)
                .clipShape(RoundedRectangle(cornerRadius: 16)).padding()
            }
        }
        .ignoresSafeArea(edges: .bottom)
        .task {
            guard ARWorldTrackingConfiguration.isSupported else {
                diagnostics = "Use a physical iPhone with AR support."; return
            }
            tracker.pause(true)
            await tracker.configure(recognition)
            permission = await AVCaptureDevice.requestAccess(for: .video)
            if !permission { diagnostics = "Enable camera access in Settings → GhostUI." }
        }
        .onChange(of: tracker.views) { _, _ in
            pendingBox = nil
            drawingMessage = "View saved. Move to another angle and draw again."
        }
        .onChange(of: selecting) { _, value in tracker.pause(value) }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active { tracker.reset("Session interrupted. Register the object again."); selecting = true }
        }
        .overlay {
            if showingControls {
                GeometryReader { geometry in
                    ZStack(alignment: .bottom) {
                        Color.black.opacity(0.3).ignoresSafeArea()
                            .contentShape(Rectangle()).onTapGesture { }
                        VStack(spacing: 0) {
                            HStack {
                                Text(deviceName).font(.headline)
                                Spacer()
                                Button("Done") { showingControls = false }
                            }.padding().background(.regularMaterial)
                            controls()
                        }
                        .frame(height: geometry.size.height * 0.65)
                        .background(.background).clipShape(RoundedRectangle(cornerRadius: 20))
                        .padding(.horizontal, 8).padding(.bottom, 8)
                    }
                }
            }
        }
    }
}

struct TrackingCameraView: UIViewRepresentable {
    let tracker: ObjectTracker
    @Binding var diagnostics: String
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func sizeThatFits(_ proposal: ProposedViewSize, uiView: ARSCNView, context: Context) -> CGSize? {
        CGSize(width: proposal.width ?? 1, height: proposal.height ?? 1)
    }
    func makeUIView(context: Context) -> ARSCNView {
        let view = ARSCNView(frame: .zero)
        view.scene = SCNScene(); view.isPlaying = true
        view.preferredFramesPerSecond = 60
        context.coordinator.view = view
        view.session.delegate = context.coordinator
        view.session.run(ARWorldTrackingConfiguration())
        return view
    }
    func updateUIView(_ view: ARSCNView, context: Context) { context.coordinator.parent = self }
    static func dismantleUIView(_ view: ARSCNView, coordinator: Coordinator) {
        view.session.pause(); view.session.delegate = nil
        coordinator.parent.tracker.reset()
    }
    final class Coordinator: NSObject, ARSessionDelegate {
        var parent: TrackingCameraView
        weak var view: ARSCNView?
        var frames = 0
        var lastOrientation: UIInterfaceOrientation?
        init(_ parent: TrackingCameraView) { self.parent = parent }
        func session(_ session: ARSession, didUpdate frame: ARFrame) {
            DispatchQueue.main.async { [weak self] in
                guard let self, let view = self.view else { return }
                let orientation: UIInterfaceOrientation
                if #available(iOS 26.0, *) {
                    orientation = view.window?.windowScene?.effectiveGeometry.interfaceOrientation ?? .portrait
                } else {
                    orientation = view.window?.windowScene?.interfaceOrientation ?? .portrait
                }
                if let previous = self.lastOrientation, previous != orientation {
                    self.parent.tracker.reset("Orientation changed. Register the object again.")
                }
                self.lastOrientation = orientation
                self.frames += 1
                if self.frames == 1 || self.frames % 60 == 0 {
                    self.parent.diagnostics = "Camera live · Frames: \(self.frames) · Tracking confidence: \(Int(self.parent.tracker.confidence * 100))%"
                }
                self.parent.tracker.process(frame, orientation: orientation, viewport: view.bounds.size, snapshot: { [weak view] in view?.snapshot() ?? UIImage() })
            }
        }
        func sessionWasInterrupted(_ session: ARSession) {
            DispatchQueue.main.async { self.parent.tracker.reset("Camera interrupted. Register the object again.") }
        }
        func sessionInterruptionEnded(_ session: ARSession) {
            DispatchQueue.main.async {
                session.run(ARWorldTrackingConfiguration(), options: [.resetTracking, .removeExistingAnchors])
                self.parent.tracker.reset("Camera resumed. Register the object again.")
            }
        }
        func session(_ session: ARSession, didFailWithError error: Error) {
            DispatchQueue.main.async {
                self.parent.tracker.reset("Camera error. Close and reopen AR.")
                self.parent.diagnostics = error.localizedDescription
            }
        }
    }
}
#endif
