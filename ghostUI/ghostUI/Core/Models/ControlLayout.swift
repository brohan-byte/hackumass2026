import Foundation

struct ControlLayout: Codable {
    struct Item: Codable {
        let bind: String
        let label: String
        let widget: String
        let group: String
    }
    let title: String
    let controls: [Item]

    static func fallback(_ capabilities: DeviceCapabilities) -> ControlLayout {
        ControlLayout(title:capabilities.name, controls:capabilities.controls.map {
            Item(bind:$0.id, label:$0.label, widget:"slider", group:"Controls")
        })
    }

    func resolvedControls(_ capabilities: DeviceCapabilities) throws -> [DeviceControl] {
        guard !title.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
              title.count <= 80, controls.count == capabilities.controls.count,
              Set(controls.map(\.bind)) == Set(capabilities.controls.map(\.id)) else {
            throw URLError(.cannotParseResponse)
        }
        return try controls.map { item in
            guard item.widget == "slider", !item.label.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
                  item.label.count <= 40, !item.group.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
                  item.group.count <= 40,
                  let original = capabilities.controls.first(where:{$0.id == item.bind}) else {
                throw URLError(.cannotParseResponse)
            }
            return DeviceControl(id:original.id, label:item.label, min:original.min,
                                 max:original.max, step:original.step)
        }
    }
}

struct ControlLayoutResponse: Decodable {
    let deviceId: String
    let layout: ControlLayout
    let source: String
    let notice: String
    let cached: Bool
}

extension ControlLayoutResponse {
    func validate(for capabilities: DeviceCapabilities) throws {
        guard deviceId == capabilities.deviceId, ["ai", "template"].contains(source) else {
            throw URLError(.cannotParseResponse)
        }
        _ = try layout.resolvedControls(capabilities)
    }
}
