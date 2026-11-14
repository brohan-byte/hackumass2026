import SwiftUI

struct ContentView: View {
    @State private var server = "http://Sais-MacBook-Pro-2.local:8780"
    @State private var token = ""
    @State private var onboarding: OnboardingSummary?
    @State private var capabilities: DeviceCapabilities?
    @State private var values: [String: Double] = [:]
    @State private var status = "Enter the server and pairing token printed by app.py --lan."
    @State private var busy = false
    @State private var showingAR = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Connect to your Mac") {
                    TextField("Server URL", text: $server)
                        .autocorrectionDisabled()
                    SecureField("Pairing token", text: $token)
                    Button("Connect") { Task { await connect() } }
                        .disabled(busy || token.isEmpty)
                }
                if let onboarding {
                    Section("Device integration") {
                        Text(onboarding.integration.name)
                        Text("Transport: " + onboarding.integration.transport).font(.caption)
                        Text("Integration selected on the Mac with --device. Test a control below to confirm the physical device, then open AR.").font(.caption)
                    }
                }
                if let caps = capabilities {
                    deviceControls(caps)
                    #if os(iOS)
                    Section {
                        Button("Open camera · Select object") { showingAR = true }.disabled(busy)
                    }
                    #endif
                }
                Section("Connection status") { Text(status).textSelection(.enabled) }
                Section { Text("Mac and iPhone must share Wi-Fi. Allow Local Network access when prompted. Connect to the selected integration, verify the device controls, then open AR to enroll or recognize its physical object.") }
            }
            .navigationTitle("GhostUI")
            #if os(iOS)
            .fullScreenCover(isPresented: $showingAR) {
                if let caps = capabilities {
                    ARScreen(deviceName:caps.name,recognition:RecognitionClient(server:server,token:token),
                             gestureControls:caps.controls,values:values,commandBusy:busy,
                             onGestureChange:{ id,value in Task { await applyGestureChange(id,value:value,caps:caps) } },
                             deviceStatus:status) {
                        Form {
                            deviceControls(caps)
                            Section("Status") { Text(status) }
                        }
                    }
                }
            }
            #endif
        }
    }

    @ViewBuilder private func deviceControls(_ caps: DeviceCapabilities) -> some View {
                    Section(caps.name + (caps.simulated ? " · SIMULATION" : "")) {
                        ForEach(caps.controls) { control in
                            VStack(alignment: .leading) {
                                Text("\(control.label): \(Int(values[control.id] ?? control.min))")
                                Slider(value: Binding(
                                    get: { values[control.id] ?? control.min },
                                    set: { values[control.id] = $0 }
                                ), in: control.min...control.max, step: control.step,
                                onEditingChanged: { editing in
                                    if !editing { Task { await send(control.id) } }
                                })
                                .disabled(busy)
                            }
                        }
                        Button("Refresh state") { Task { await refresh() } }.disabled(busy)
                    }
    }

    private func request<T: Decodable>(_ path: String, body: [String: Any]? = nil) async throws -> T {
        try await GhostAPIClient(server:server,token:token).request(path,body:body)
    }

    @MainActor private func applyGestureChange(_ id: String, value: Int, caps: DeviceCapabilities) async {
        guard !busy, let control = caps.controls.first(where: { $0.id == id }) else { return }
        busy = true; defer { busy = false }
        do {
            // Slider release supplies an absolute value bounded by trusted capabilities.
            let target = Int(max(control.min,min(control.max,Double(value))))
            status = "Sending gesture \(control.label)…"
            values = try await request("/mobile/command", body:["capability":id,"value":target])
            status = "Confirmed \(control.label): \(Int(values[id] ?? Double(target)))"
        } catch { status = "Gesture not confirmed: " + error.localizedDescription }
    }

    @MainActor private func connect() async {
        busy = true; capabilities = nil; onboarding = nil; status = "Connecting…"
        defer { busy = false }
        do {
            let client = OnboardingClient(api:GhostAPIClient(server:server,token:token))
            let summary = try await client.status()
            let caps: DeviceCapabilities = try await request("/mobile/capabilities")
            let verified = try await client.verifyConnection()
            values = verified.state; capabilities = caps; onboarding = summary
            status = "Connected to \(caps.name). State confirmed. Test a control to confirm the physical device."
        } catch { status = error.localizedDescription }
    }
    @MainActor private func refresh() async {
        guard !busy else { return }; busy = true
        defer { busy = false }
        do { values = try await request("/mobile/state"); status = "State refreshed." }
        catch { status = "State unavailable: " + error.localizedDescription }
    }
    @MainActor private func send(_ id: String) async {
        guard !busy, let value = values[id] else { return }; busy = true
        status = "Sending \(id)…"; defer { busy = false }
        do {
            values = try await request("/mobile/command", body: ["capability": id, "value": Int(value)])
            status = "Confirmed \(id): \(Int(values[id] ?? value))"
        } catch { status = "Not confirmed: " + error.localizedDescription }
    }
}
