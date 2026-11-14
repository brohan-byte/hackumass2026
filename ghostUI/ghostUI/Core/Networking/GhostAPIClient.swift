import Foundation

/// Paired Mac transport shared by onboarding and device controls.
struct GhostAPIClient: Sendable {
    let server: String
    let token: String
    func request<T: Decodable>(_ path: String, body: [String: Any]? = nil, timeout: TimeInterval = 35) async throws -> T {
        let address = server.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let base = URL(string: address), base.scheme == "http" || base.scheme == "https",
              base.host != nil, let url = URL(string: address.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + path)
        else { throw URLError(.badURL) }
        var req = URLRequest(url: url)
        req.timeoutInterval = timeout
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

}
