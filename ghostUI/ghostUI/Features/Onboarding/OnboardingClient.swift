import Foundation

struct IntegrationDescription: Decodable, Identifiable {
    let id: String
    let name: String
    let transport: String
    let setup: String
    let simulationOnly: Bool
}
struct OnboardingSummary: Decodable {
    let integration: IntegrationDescription
    let selectedIntegration: String
    let deviceId: String
    let scope: String
}
struct ConnectionVerification: Decodable {
    let state: [String:Double]
    let connectionVerified: Bool
    let physicalIdentityConfirmed: Bool
}
struct OnboardingClient {
    let api: GhostAPIClient
    func status() async throws -> OnboardingSummary {
        try await api.request("/mobile/onboarding")
    }
    func verifyConnection() async throws -> ConnectionVerification {
        try await api.request("/mobile/onboarding/verify",body:[:])
    }
}
