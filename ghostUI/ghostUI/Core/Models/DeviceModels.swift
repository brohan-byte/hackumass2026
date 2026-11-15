import Foundation

struct DeviceControl: Decodable, Identifiable {
    let id: String
    let label: String
    let min: Double
    let max: Double
    let step: Double
}
struct DeviceCapabilities: Decodable {
    let deviceId: String
    let name: String
    let simulated: Bool
    let controls: [DeviceControl]
}


struct IntegrationDescription: Decodable, Identifiable {
    let id: String
    let name: String
    let transport: String
    let setup: String
    let simulationOnly: Bool
}
struct SavedDevice: Decodable, Identifiable {
    let id: String
    let name: String
    let integrationId: String
    let address: String?
    let simulated: Bool
    let status: String
    let error: String?
}

struct SavedDevicesResponse: Decodable {
    let devices: [SavedDevice]
    let activeDeviceId: String?
    let integrations: [IntegrationDescription]
}

struct RegistrationChoice: Decodable, Identifiable {
    let id: String
    let name: String
}
struct RegistrationChoices: Decodable {
    let devices: [RegistrationChoice]
    let notice: String?
}
struct RegisteredObject: Decodable {
    let deviceId: String
}

struct DeviceSetupJob: Decodable {
    let id: String
    let status: String
    let message: String
    let deviceId: String?
    let error: String?
}
