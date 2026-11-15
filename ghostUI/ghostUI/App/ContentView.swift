import SwiftUI

/// Protocol selection, persistence and simulation belong to the Mac backend.
struct ContentView: View {
    @State private var server="http://Sais-MacBook-Pro-2.local:8780"
    @State private var token=""
    @State private var connected=false
    @State private var showingSettings=true
    @State private var showingRegistration=false
    @State private var showingEnrollment=false
    @State private var choices: [RegistrationChoice]=[]
    @State private var discoveredChoices: [RegistrationChoice]=[]
    @State private var findingNewDevice=false
    @State private var setupMessage="Finding devices…"
    @State private var registrationNotice: String?
    @State private var confirmingObject=false
    @State private var busy=false
    @State private var status="Enter the server address and pairing code from your Mac."
    @State private var capabilities: DeviceCapabilities?
    @State private var values: [String:Double]=[:]
    @State private var arLayout: ControlLayout?
    @State private var layoutNotice=""

    private var api: GhostAPIClient { GhostAPIClient(server:server,token:token) }
    private func deviceAPI(_ id: String) -> GhostAPIClient {
        GhostAPIClient(server:server,token:token,deviceID:id)
    }

    var body: some View {
        #if os(iOS)
        SceneScreen(recognition:RecognitionClient(server:server,token:token,isScene:true),
            connected:connected,paused:showingSettings || showingRegistration,
            capabilities:capabilities,layout:arLayout,layoutNotice:layoutNotice,
            values:values,commandBusy:busy,status:status,
            onSelect:{ try await openObject($0) },
            onCommit:{ id,value in Task { await sendValue(id,value:value) } },
            onRegister:{ showingRegistration=true },onSettings:{ showingSettings=true }) {
                Form { touchControls() }
            }
            .preferredColorScheme(.dark)
            .onChange(of:server) { _,_ in connected=false;capabilities=nil }
            .onChange(of:token) { _,_ in connected=false;capabilities=nil }
            .sheet(isPresented:$showingSettings) { connectionSettings }
            .sheet(isPresented:$showingRegistration,onDismiss:{ confirmingObject=false;findingNewDevice=false }) { registration }
        #else
        connectionSettings
        #endif
    }

    private var connectionSettings: some View {
        NavigationStack {
            Form {
                Section("Connect to Mac") {
                    TextField("Server address",text:$server).autocorrectionDisabled()
                    SecureField("Pairing code",text:$token)
                    Button("Connect") { Task { await connect() } }.disabled(busy || token.isEmpty)
                }.disabled(busy)
                Section { Text(status).font(.callout).textSelection(.enabled) }
            }
            .navigationTitle("Connection")
            .toolbar { ToolbarItem(placement:.confirmationAction) { Button("Done") { showingSettings=false } } }
        }
    }

    private var registration: some View {
        NavigationStack {
            Group {
                if confirmingObject,let caps=capabilities {
                    Form {
                        Section {
                            Text(caps.name).font(.headline)
                            Text("Move the slider and check that this is the object you want to register.")
                            if let control=caps.controls.first { slider(control) }
                        }
                        Section {
                            Button("That's my device · Continue") { showingEnrollment=true }.disabled(busy)
                        }
                        if !status.isEmpty { Section { Text(status).font(.caption) } }
                    }
                } else {
                    List {
                        Section {
                            Text("Which device are you registering?").foregroundStyle(.secondary)
                            ForEach(findingNewDevice ? discoveredChoices : choices) { choice in
                                Button(choice.name) {
                                    Task {
                                        if findingNewDevice { await prepareDiscoveredDevice(choice.id) }
                                        else { await chooseForRegistration(choice.id) }
                                    }
                                }.disabled(busy)
                            }
                            if busy { ProgressView(setupMessage) }
                            else if (findingNewDevice ? discoveredChoices : choices).isEmpty {
                                Text("Keep your light and Mac on the same Wi-Fi, then search again.")
                            }
                        }
                        if let registrationNotice { Section { Text(registrationNotice).font(.caption) } }
                        Section {
                            Button(findingNewDevice ? "Search again" : "Find new device") {
                                Task { await findDevices() }
                            }.disabled(busy)
                            if findingNewDevice && !choices.isEmpty {
                                Button("Saved devices") { findingNewDevice=false;registrationNotice=nil }.disabled(busy)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Register object")
            .toolbar { ToolbarItem(placement:.cancellationAction) { Button("Cancel") { showingRegistration=false }.disabled(busy) } }
            .interactiveDismissDisabled(busy)
            .task { confirmingObject=false;findingNewDevice=false;await loadChoices() }
            #if os(iOS)
            .fullScreenCover(isPresented:$showingEnrollment,onDismiss:{ showingRegistration=false }) {
                if let caps=capabilities {
                    let layout=arLayout ?? ControlLayout.fallback(caps)
                    ARScreen(deviceName:caps.name,layoutTitle:layout.title,
                        layoutGroups:Dictionary(uniqueKeysWithValues:layout.controls.map{($0.bind,$0.group)}),
                        layoutNotice:"",recognition:RecognitionClient(server:server,token:token,deviceID:caps.deviceId),
                        gestureControls:(try? layout.resolvedControls(caps)) ?? caps.controls,
                        values:values,commandBusy:busy,
                        onGestureChange:{ id,value in Task { await sendValue(id,value:value) } },
                        deviceStatus:status,registrationOnly:true) { Form { touchControls() } }
                }
            }
            #endif
        }
    }

    @ViewBuilder private func touchControls() -> some View {
        if let caps=capabilities {
            Section(caps.name) { ForEach(caps.controls) { slider($0) } }
            Section { Text(status).font(.caption) }
        }
    }
    private func slider(_ control: DeviceControl) -> some View {
        VStack(alignment:.leading) {
            Text("\(control.label): \(Int(values[control.id] ?? control.min))")
            Slider(value:Binding(get:{values[control.id] ?? control.min},set:{values[control.id]=$0}),
                in:control.min...control.max,step:control.step,onEditingChanged:{ editing in
                    if !editing,let value=values[control.id] { Task { await sendValue(control.id,value:Int(value)) } }
                }).disabled(busy)
        }
    }

    @MainActor private func connect() async {
        guard !busy else { return }
        busy=true;connected=false;capabilities=nil;arLayout=nil;values=[:]
        status="Connecting…";defer{busy=false}
        do {
            let _: SavedDevicesResponse = try await api.request("/mobile/devices")
            connected=true;status="Connected.";showingSettings=false
        } catch { status=error.localizedDescription }
    }
    @MainActor private func loadChoices() async {
        guard !busy else { return }
        busy=true;registrationNotice=nil;setupMessage="Finding devices…";defer{busy=false}
        do {
            let result: RegistrationChoices = try await api.request("/mobile/registration")
            choices=result.devices;registrationNotice=result.notice
            if choices.isEmpty { try await discoverDevices() }
        } catch { choices=[];registrationNotice=error.localizedDescription }
    }
    @MainActor private func discoverDevices() async throws {
        findingNewDevice=true;discoveredChoices=[];setupMessage="Looking for lights…"
        let result: RegistrationChoices = try await api.request("/mobile/setup/discover",body:[:],timeout:25)
        discoveredChoices=result.devices;registrationNotice=result.notice
    }
    @MainActor private func findDevices() async {
        guard !busy else { return }
        busy=true;registrationNotice=nil;defer{busy=false}
        do { try await discoverDevices() }
        catch { registrationNotice=error.localizedDescription }
    }
    @MainActor private func prepareDiscoveredDevice(_ candidate: String) async {
        guard !busy else { return }
        busy=true;registrationNotice=nil;setupMessage="Connecting to your light…";defer{busy=false}
        do {
            var job: DeviceSetupJob = try await api.request("/mobile/setup/start",body:["candidateId":candidate])
            let deadline=Date().addingTimeInterval(150)
            while job.status == "running" {
                setupMessage=job.message
                guard Date()<deadline else { throw URLError(.timedOut) }
                try await Task.sleep(for:.milliseconds(600))
                job=try await api.request("/mobile/setup/jobs/"+job.id)
            }
            guard job.status == "ready",let id=job.deviceId else {
                throw NSError(domain:"GhostUI",code:1,userInfo:[NSLocalizedDescriptionKey:job.error ?? job.message])
            }
            setupMessage="Opening your controls…"
            try await loadControls(id)
            confirmingObject=true
        } catch { registrationNotice=error.localizedDescription }
    }
    @MainActor private func chooseForRegistration(_ candidate: String) async {
        guard !busy else { return }
        busy=true;registrationNotice=nil;setupMessage="Opening your controls…";defer{busy=false}
        do {
            let result: RegisteredObject = try await api.request("/mobile/registration",body:["deviceId":candidate],timeout:90)
            try await loadControls(result.deviceId)
            confirmingObject=true
        } catch { registrationNotice="Could not connect. " + error.localizedDescription }
    }
    @MainActor private func openObject(_ id: String) async throws {
        guard !busy else { throw URLError(.cancelled) }
        busy=true;defer{busy=false}
        let _: SavedDevicesResponse = try await api.request("/mobile/devices/"+id+"/select",body:[:],timeout:90)
        try await loadControls(id)
    }
    @MainActor private func loadControls(_ id: String) async throws {
        capabilities=nil;arLayout=nil;values=[:];status="Connecting…"
        let scoped=deviceAPI(id)
        let caps: DeviceCapabilities = try await scoped.request("/mobile/capabilities")
        guard caps.deviceId==id,!caps.simulated else { throw URLError(.badServerResponse) }
        let verified=try await OnboardingClient(api:scoped).verifyConnection()
        guard verified.connectionVerified else { throw URLError(.badServerResponse) }
        values=verified.state
        do {
            let result: ControlLayoutResponse = try await scoped.request("/mobile/layout",body:["refresh":false])
            try result.validate(for:caps)
            arLayout=result.layout;layoutNotice=result.notice
        } catch { arLayout=ControlLayout.fallback(caps);layoutNotice="" }
        capabilities=caps;status="Ready."
    }
    @MainActor private func sendValue(_ id: String,value: Int) async {
        guard !busy,let caps=capabilities,let control=caps.controls.first(where:{$0.id==id}) else { return }
        busy=true;status="Applying…";defer{busy=false}
        do {
            let target=Int(max(control.min,min(control.max,Double(value))))
            values=try await deviceAPI(caps.deviceId).request("/mobile/command",body:["capability":id,"value":target])
            status="Confirmed \(control.label): \(Int(values[id] ?? Double(target)))"
        } catch { status="Change not confirmed. " + error.localizedDescription }
    }
}
