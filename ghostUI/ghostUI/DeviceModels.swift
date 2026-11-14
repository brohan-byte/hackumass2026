import Foundation

struct DeviceControl: Decodable, Identifiable {
    let id: String
    let label: String
    let min: Double
    let max: Double
    let step: Double
}
struct DeviceCapabilities: Decodable {
    let name: String
    let simulated: Bool
    let controls: [DeviceControl]
}

