#if os(iOS)
import SwiftUI
import ARKit
import AVFoundation

/// Main experience: recognize saved objects, then open the matching controls.
struct SceneScreen<Controls: View>: View {
    let recognition: RecognitionClient
    let connected: Bool
    let paused: Bool
    let capabilities: DeviceCapabilities?
    let layout: ControlLayout?
    let layoutNotice: String
    let values: [String:Double]
    let commandBusy: Bool
    let status: String
    let onSelect: (String) async throws -> Void
    let onCommit: (String,Int) -> Void
    let onRegister: () -> Void
    let onSettings: () -> Void
    @ViewBuilder var controls: () -> Controls
    @StateObject private var tracker=ObjectTracker()
    @StateObject private var hand=HandGestureController()
    @Environment(\.scenePhase) private var scenePhase
    private enum Mode { case camera, loading, hud, touch }
    @State private var mode: Mode = .camera
    @State private var permission=false
    @State private var diagnostics="Waiting for camera…"
    @State private var error: String?
    @State private var touchingObject=false

    private var sliders: [DeviceControl] {
        guard let capabilities else { return [] }
        return Array(((try? layout?.resolvedControls(capabilities)) ?? capabilities.controls).prefix(3))
    }

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment:.top) {
                Color.black.ignoresSafeArea()
                if permission && ARWorldTrackingConfiguration.isSupported {
                    TrackingCameraView(tracker:tracker,handGestures:hand,
                        pauseObjects:mode != .camera || paused,diagnostics:$diagnostics)
                        .frame(width:geometry.size.width,height:geometry.size.height)
                    if mode == .camera {
                        ForEach(tracker.sceneObjects) { object in
                            ObjectSelectionOverlay(box:object.box,contour:object.contour,
                                selecting:false,deviceName:object.name,onRegister:{ _ in },
                                onSelect:{ choose(object.id) },
                                onSelectionBegan:{ touchingObject=true;updateSelectionInteraction() },
                                onSelectionEnded:{ touchingObject=false;updateSelectionInteraction() })
                        }
                        HandCursorOverlay(hand:hand)
                    }
                }
                if mode == .camera || mode == .loading {
                    VStack {
                        HStack {
                            Text("GhostUI").font(.headline)
                            Spacer()
                            Button(action:onSettings) { Image(systemName:"gearshape") }
                                .accessibilityLabel("Connection settings")
                        }.padding().background(.ultraThinMaterial).clipShape(Capsule())
                        Spacer()
                        if mode == .loading { ProgressView("Opening controls…").padding().background(.regularMaterial).clipShape(Capsule()) }
                        else {
                            VStack(spacing:12) {
                                Text(cameraMessage).font(.callout).multilineTextAlignment(.center).lineLimit(3)
                                Button("Register object",action:onRegister)
                                    .buttonStyle(.borderedProminent).tint(.mint).foregroundStyle(.black)
                                    .disabled(!connected || !permission)
                            }.padding().frame(maxWidth:.infinity).background(.ultraThinMaterial)
                                .clipShape(RoundedRectangle(cornerRadius:20))
                        }
                    }.padding()
                }
                if mode == .hud,let capabilities {
                    GestureControlOverlay(deviceName:capabilities.name,layoutTitle:layout?.title ?? capabilities.name,
                        groups:Dictionary(uniqueKeysWithValues:(layout?.controls ?? []).map{($0.bind,$0.group)}),
                        layoutNotice:"",controls:sliders,values:values,hand:hand,deviceStatus:status,
                        onBack:{ returnToCamera() },onClose:{ returnToCamera() },onTouch:{ mode = .touch })
                }
                if mode == .touch {
                    VStack {
                        Spacer()
                        VStack(spacing:0) {
                            HStack {
                                Button("Gestures") { mode = .hud };Spacer()
                                Button("Back to camera") { returnToCamera() }
                            }.padding().background(.regularMaterial)
                            controls()
                        }.frame(height:geometry.size.height*0.6).background(.background)
                            .clipShape(RoundedRectangle(cornerRadius:20))
                    }.padding(8)
                }
            }
        }
        .foregroundStyle(.white)
        .task(id:connected) {
            permission=await AVCaptureDevice.requestAccess(for:.video)
            if connected { await tracker.configure(recognition) }
            hand.onSelectObject={ choose($0) }
            hand.onBack={ returnToCamera() }
            hand.onClose={ returnToCamera() }
            hand.onCommit=onCommit
            syncMode()
        }
        .onChange(of:mode) { _,_ in touchingObject=false;syncMode() }
        .onChange(of:hand.cursor != nil) { _,_ in updateSelectionInteraction() }
        .onChange(of:paused) { _,value in
            syncMode()
            if !value && connected { Task { await tracker.configure(recognition);syncMode() } }
        }
        .onChange(of:commandBusy) { _,value in hand.setCommandBusy(value) }
        .onChange(of:scenePhase) { _,phase in
            if phase == .active { syncMode() }
            else { tracker.pause(true);hand.setMode(.off) }
        }
        .onDisappear { tracker.pause(true);hand.setMode(.off) }
    }

    private var cameraMessage: String {
        if !permission { return "Allow camera access in Settings to recognize objects." }
        if !ARWorldTrackingConfiguration.isSupported { return "Open GhostUI on an AR-capable iPhone." }
        if !connected { return "Connect to your Mac using the settings button." }
        if let error { return error }
        return tracker.message
    }
    private func choose(_ id: String) {
        guard mode == .camera,!paused,tracker.canSelectSceneObject(id) else { return }
        error=nil;mode = .loading
        syncMode()
        Task {
            do { try await onSelect(id);mode = .hud }
            catch { self.error="Could not open controls. " + error.localizedDescription;mode = .camera }
        }
    }
    private func updateSelectionInteraction() {
        tracker.setSelectionInteraction(mode == .camera && (touchingObject || hand.cursor != nil))
    }
    private func returnToCamera() { error=nil;mode = .camera }
    private func syncMode() {
        tracker.pause(mode != .camera || paused || !connected || !permission)
        if mode == .hud && !paused { hand.setMode(.hud,controls:sliders.map(\.id)) }
        else if mode == .camera && connected && !paused && permission { hand.setMode(.deviceSelection) }
        else { hand.setMode(.off) }
        hand.setCommandBusy(commandBusy)
    }
}
#endif
