import SwiftUI

struct ContentView: View {
    @State private var server = "http://Sais-MacBook-Pro-2.local:8780"
    @State private var token = ""
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
                if let caps = capabilities {
                    deviceControls(caps)
                    #if os(iOS)
                    Section {
                        Button("Open camera · Select object") { showingAR = true }.disabled(busy)
                    }
                    #endif
                }
                Section("Connection status") { Text(status).textSelection(.enabled) }
                Section { Text("Mac and iPhone must share Wi-Fi. Allow Local Network access when prompted. This first version tests connectivity; AR comes next.") }
            }
            .navigationTitle("GhostUI")
            #if os(iOS)
            .fullScreenCover(isPresented: $showingAR) {
                if let caps = capabilities {
                    ARScreen(deviceName: caps.name, recognition: RecognitionClient(server: server, token: token)) {
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
        let address = server.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let base = URL(string: address), base.scheme == "http" || base.scheme == "https",
              base.host != nil, let url = URL(string: address.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + path)
        else { throw URLError(.badURL) }
        var req = URLRequest(url: url)
        req.timeoutInterval = 35
        req.setValue("Bearer " + token.trimmingCharacters(in: .whitespacesAndNewlines), forHTTPHeaderField: "Authorization")
        if let body {
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        guard (200..<300).contains(http.statusCode) else {
            let message = (try? JSONDecoder().decode([String: String].self, from: data))?["error"] ?? "HTTP \(http.statusCode)"
            throw NSError(domain: "GhostUI", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: message])
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    @MainActor private func connect() async {
        busy = true; capabilities = nil; status = "Connecting…"
        defer { busy = false }
        do {
            let caps: DeviceCapabilities = try await request("/mobile/capabilities")
            let state: [String: Double] = try await request("/mobile/state")
            values = state; capabilities = caps; status = "Connected to \(caps.name). State confirmed."
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
