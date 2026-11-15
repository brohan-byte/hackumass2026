import SwiftUI
#if os(iOS)
import ARKit
import SceneKit
import AVFoundation
import UIKit

struct ARScreen<Controls: View>: View {
    let deviceName: String
    let layoutTitle: String
    let layoutGroups: [String:String]
    let layoutNotice: String
    let recognition: RecognitionClient
    let gestureControls: [DeviceControl]
    let values: [String:Double]
    let commandBusy: Bool
    let onGestureChange: (String,Int) -> Void
    let deviceStatus: String
    @ViewBuilder var controls: () -> Controls
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var tracker = ObjectTracker()
    @StateObject private var hand = HandGestureController()
    private enum Mode { case camera, hud, touch }
    @State private var mode: Mode = .camera
    @State private var handsEnabled = true
    @State private var permission = false
    @State private var selecting = true
    @State private var pendingBox: CGRect?
    @State private var drawingMessage = "Drag below this panel to select the device."
    @State private var diagnostics = "Waiting for camera"

    private var supportedControls: [DeviceControl] { Array(gestureControls.prefix(3)) }
    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment:.top) {
                Color.black
                if permission && ARWorldTrackingConfiguration.isSupported {
                    TrackingCameraView(tracker:tracker,handGestures:hand,
                                       pauseObjects:mode != .camera,diagnostics:$diagnostics)
                        .frame(width:geometry.size.width,height:geometry.size.height)
                    if mode == .camera {
                        if selecting, let preview = tracker.enrollmentPreview {
                            Image(uiImage:preview).resizable()
                                .frame(width:geometry.size.width,height:geometry.size.height)
                                .allowsHitTesting(false)
                        }
                        ObjectSelectionOverlay(box:selecting ? pendingBox : tracker.box,
                            contour:selecting ? [] : tracker.contour,selecting:selecting,
                            deviceName:deviceName,
                            onBeginRegistration:{ tracker.stageEnrollmentImage() },
                            onRegister:{ rect in
                                pendingBox=rect
                                Task { await saveEnrollment(rect) }
                            },
                            onSelect:{ mode = .hud },
                            onInvalid:{ tracker.discardEnrollmentImage();pendingBox=nil;drawingMessage="Draw a larger box below this panel." })
                            .allowsHitTesting(!tracker.enrolling)
                    }
                }
                if mode == .camera {
                    VStack(spacing:7) {
                        HStack {
                            Button("Close") { dismiss() };Spacer()
                            Button("Add view") { tracker.reset();tracker.discardEnrollmentImage();pendingBox=nil;selecting=true }
                                .disabled(!permission || tracker.enrolling || tracker.views>=4)
                        }
                        HStack {
                            Text("Views: \(tracker.views)/4").font(.caption);Spacer()
                            Button("Clear") { Task { await tracker.clearEnrollment();tracker.discardEnrollmentImage();pendingBox=nil;selecting=true } }
                                .disabled(tracker.enrolling)
                        }
                        if selecting {
                            Text(drawingMessage).font(.caption)
                            HStack {
                                if tracker.enrolling {
                                    ProgressView("Saving view…")
                                } else if let pendingBox {
                                    Button("Retry saving") { Task { await saveEnrollment(pendingBox) } }
                                    Button("Redraw") { self.pendingBox=nil;tracker.discardEnrollmentImage() }
                                } else {
                                    Text("Draw a box around the object. It saves when you lift your finger.").font(.caption)
                                }
                            }
                        } else {
                            Toggle("Finger cursor",isOn:$handsEnabled).font(.caption)
                            Text(hand.message).font(.caption).multilineTextAlignment(.center)
                        }
                        Text(tracker.message).font(.caption).multilineTextAlignment(.center)
                        Text(diagnostics).font(.caption2.monospaced()).foregroundStyle(.secondary)
                        Button("Touch controls") { mode = .touch }.font(.caption)
                    }.padding().background(.ultraThinMaterial)
                        .clipShape(RoundedRectangle(cornerRadius:16)).padding()
                    if !selecting && handsEnabled { HandCursorOverlay(hand:hand) }
                }
            }
        }
        .ignoresSafeArea(edges:.bottom)
        .task {
            hand.onSelectDevice={ mode = .hud }
            hand.onBack={ mode = .camera }
            hand.onClose={ dismiss() }
            hand.onCommit=onGestureChange
            tracker.pause(true)
            await tracker.configure(recognition)
            guard ARWorldTrackingConfiguration.isSupported else { diagnostics="AR unavailable on this device.";return }
            permission=await AVCaptureDevice.requestAccess(for:.video)
            if !permission { diagnostics="Enable camera access in Settings → GhostUI." }
            // Reuse saved enrollment immediately; new devices still open registration.
            selecting = !(tracker.ready && tracker.views > 0)
            syncMode()
        }
        .onChange(of:tracker.views) { _,views in
            pendingBox=nil
            drawingMessage="View saved. Use Add view to register another angle."
            if views == 0 { selecting=true }
            else if tracker.ready { selecting=false }
            syncMode()
        }
        .onChange(of:mode) { _,_ in syncMode() }
        .onChange(of:handsEnabled) { _,_ in syncMode() }
        .onChange(of:selecting) { _,_ in syncMode() }
        .onChange(of:commandBusy) { _,value in hand.setCommandBusy(value) }
        .onChange(of:scenePhase) { _,phase in
            if phase != .active { hand.setMode(.off);tracker.pause(true) }
            else { syncMode() }
        }
        .onDisappear { hand.setMode(.off);tracker.pause(true);tracker.discardEnrollmentImage() }
        .overlay {
            if mode == .hud {
                GestureControlOverlay(deviceName:deviceName,layoutTitle:layoutTitle,groups:layoutGroups,
                    layoutNotice:layoutNotice,controls:supportedControls,values:values,
                    hand:hand,deviceStatus:deviceStatus,onBack:{ mode = .camera },
                    onClose:{ dismiss() },onTouch:{ mode = .touch })
            } else if mode == .touch {
                GeometryReader { geometry in
                    ZStack(alignment:.bottom) {
                        Color.black.opacity(0.3).ignoresSafeArea().contentShape(Rectangle()).onTapGesture { }
                        VStack(spacing:0) {
                            HStack {
                                Button("Gesture HUD") { mode = .hud };Spacer()
                                Button("Back") { mode = .camera }
                            }.padding().background(.regularMaterial)
                            controls()
                        }.frame(height:geometry.size.height*0.65)
                            .background(.background).clipShape(RoundedRectangle(cornerRadius:20)).padding(8)
                    }
                }
            }
        }
    }
    @MainActor private func saveEnrollment(_ rect: CGRect) async {
        drawingMessage = "Saving the selected view…"
        if await tracker.select(rect) {
            pendingBox=nil;selecting=false
            drawingMessage="View saved. Use Add view for another angle."
            syncMode()
        } else {
            drawingMessage="View not saved. Retry or redraw below."
        }
    }

    private func syncMode() {
        let paused=mode != .camera || selecting || !permission || !tracker.ready || tracker.views == 0
        tracker.pause(paused)
        if mode == .hud { hand.setMode(.hud,controls:supportedControls.map(\.id)) }
        else if mode == .camera && !selecting && handsEnabled { hand.setMode(.deviceSelection) }
        else { hand.setMode(.off) }
        hand.setCommandBusy(commandBusy)
        if !paused { tracker.reset("Looking for the enrolled device…") }
    }
}

struct TrackingCameraView: UIViewRepresentable {
    let tracker: ObjectTracker
    let handGestures: HandGestureController
    let pauseObjects: Bool
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
                    self.parent.handGestures.cancelGesture()
                }
                self.lastOrientation = orientation
                self.frames += 1
                if self.frames == 1 || self.frames % 60 == 0 {
                    self.parent.diagnostics = "Camera live · Frames: \(self.frames) · Tracking confidence: \(Int(self.parent.tracker.confidence * 100))%"
                }
                if !self.parent.pauseObjects { self.parent.handGestures.setDeviceBox(self.parent.tracker.box) }
                self.parent.handGestures.process(frame,orientation:orientation,viewport:view.bounds.size)
                if !self.parent.pauseObjects {
                    self.parent.tracker.process(frame, orientation: orientation, viewport: view.bounds.size, snapshot: { [weak view] in view?.snapshot() ?? UIImage() })
                }
            }
        }
        func sessionWasInterrupted(_ session: ARSession) {
            DispatchQueue.main.async {
                self.parent.handGestures.cancelGesture()
                self.parent.tracker.reset("Camera interrupted. Register the object again.")
            }
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
