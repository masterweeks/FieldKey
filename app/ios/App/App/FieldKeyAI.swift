import Foundation
import Capacitor
#if canImport(FoundationModels)
import FoundationModels
#endif

/// Email import with Apple's on-device model (Foundation Models, iOS 26, Apple Intelligence on:
/// iPhone 15 Pro or newer). Nothing leaves the phone. index.html still runs its rules-based parser
/// and only uses what the model finds to fill gaps, after checking it against the email text.
/// JS: Capacitor.nativePromise("FieldKeyAI", "available", {}) -> {value: Bool, reason: String}
///     Capacitor.nativePromise("FieldKeyAI", "parseEmail", {text}) -> {sites: [{sapId, name, address, phones, access, notes}]}
@objc(FieldKeyAIPlugin)
public class FieldKeyAIPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "FieldKeyAIPlugin"
    public let jsName = "FieldKeyAI"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "available", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "parseEmail", returnType: CAPPluginReturnPromise)
    ]

    @objc func available(_ call: CAPPluginCall) {
        #if canImport(FoundationModels)
        if #available(iOS 26.0, *) {
            switch SystemLanguageModel.default.availability {
            case .available:
                call.resolve(["value": true, "reason": ""])
            case .unavailable(.deviceNotEligible):
                call.resolve(["value": false, "reason": "device"])
            case .unavailable(.appleIntelligenceNotEnabled):
                call.resolve(["value": false, "reason": "off"])
            case .unavailable(.modelNotReady):
                call.resolve(["value": false, "reason": "downloading"])
            default:
                call.resolve(["value": false, "reason": "unavailable"])
            }
            return
        }
        #endif
        call.resolve(["value": false, "reason": "ios"])
    }

    @objc func parseEmail(_ call: CAPPluginCall) {
        let text = call.getString("text") ?? ""
        #if canImport(FoundationModels)
        if #available(iOS 26.0, *) {
            Task {
                do {
                    let sites = try await EmailReader.read(text)
                    call.resolve(["sites": sites])
                } catch {
                    call.reject("On-device AI couldn't read that email: \(error.localizedDescription)")
                }
            }
            return
        }
        #endif
        call.reject("On-device AI needs iOS 26", "UNAVAILABLE")
    }
}

#if canImport(FoundationModels)
@available(iOS 26.0, *)
@Generable
struct ParsedSite {
    @Guide(description: "The SAP equipment ID exactly as written, digits only (usually 9 digits)")
    var sapId: String
    @Guide(description: "The customer's name as written, or empty")
    var name: String
    @Guide(description: "The site's street address as written, or empty")
    var address: String
    @Guide(description: "The customer's phone numbers as written; not the requestor's")
    var phones: [String]
    @Guide(description: "Short access status if given, e.g. 'Gate locked' or 'OK to access', or empty")
    var access: String
    @Guide(description: "Other access details as written: gate codes, dogs, best times, who to call. Empty if none")
    var notes: String
}

@available(iOS 26.0, *)
@Generable
struct ParsedEmail {
    @Guide(description: "One entry per SAP equipment ID in the email")
    var sites: [ParsedSite]
}

@available(iOS 26.0, *)
enum EmailReader {
    static let instructions = """
    You read email replies about utility inspection sites. Each site is identified by an SAP \
    equipment ID, usually 9 digits. List every site in the email with its details. Copy names, \
    addresses, phone numbers and notes exactly as they are written. If the email doesn't say \
    something, leave it empty. Never guess or make anything up. Ignore the sender's own details, \
    such as lines starting with "Requestor", signatures and disclaimers.
    """

    /// The on-device model has a small context window, so long emails are read in parts, split at
    /// blank lines and before lines that start a new site.
    static func read(_ text: String) async throws -> [[String: Any]] {
        var out: [[String: Any]] = []
        for part in chunks(text, limit: 3500) {
            let session = LanguageModelSession(instructions: instructions)
            let reply = try await session.respond(to: "Email:\n\(part)", generating: ParsedEmail.self,
                                                  options: GenerationOptions(temperature: 0))
            for s in reply.content.sites {
                out.append(["sapId": s.sapId, "name": s.name, "address": s.address,
                            "phones": s.phones, "access": s.access, "notes": s.notes])
            }
        }
        return out
    }

    static func chunks(_ text: String, limit: Int) -> [String] {
        if text.count <= limit { return [text] }
        var parts: [String] = []
        var current = ""
        for line in text.components(separatedBy: "\n") {
            let startsSite = line.range(of: #"(?i)\bSAP\b|\b\d{9}\b"#, options: .regularExpression) != nil
            if current.count + line.count > limit || (startsSite && current.count > limit / 2) {
                if !current.isEmpty { parts.append(current) }
                current = ""
            }
            current += line + "\n"
        }
        if !current.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { parts.append(current) }
        return parts
    }
}
#endif
