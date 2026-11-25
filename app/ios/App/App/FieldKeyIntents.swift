import Foundation
import Capacitor
import AppIntents

/// Siri and Shortcuts: "Text the next site in FieldKey". Opens FieldKey, which brings up the next
/// un-texted site's message in the guided flow (textNextSite() in index.html).
/// The intent leaves the request with FieldKeyIntentsPlugin; the page collects it with
/// Capacitor.nativePromise("FieldKeyIntents", "takePending", {}) on start, when it comes back to
/// the front, and on the window event "fieldkeyaction".
@available(iOS 16.0, *)
struct TextNextSiteIntent: AppIntent {
    static var title: LocalizedStringResource = "Text the next site"
    static var description = IntentDescription("Opens FieldKey with the next site's text ready to send.")
    static var openAppWhenRun: Bool = true

    @MainActor
    func perform() async throws -> some IntentResult {
        FieldKeyIntentsPlugin.request("textNext")
        return .result()
    }
}

@available(iOS 17.0, *)
struct FieldKeyShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: TextNextSiteIntent(),
                    phrases: ["Text the next site in \(.applicationName)",
                              "Next text in \(.applicationName)"],
                    shortTitle: "Text next site",
                    systemImageName: "message")
    }
}

@objc(FieldKeyIntentsPlugin)
public class FieldKeyIntentsPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "FieldKeyIntentsPlugin"
    public let jsName = "FieldKeyIntents"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "takePending", returnType: CAPPluginReturnPromise)
    ]

    private static var pending: String?
    private static weak var current: FieldKeyIntentsPlugin?

    override public func load() {
        FieldKeyIntentsPlugin.current = self
    }

    /// Called by an intent: keep the request until the page takes it, and nudge the page if it's running.
    static func request(_ action: String) {
        pending = action
        current?.bridge?.triggerWindowJSEvent(eventName: "fieldkeyaction")
    }

    @objc func takePending(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            let action = FieldKeyIntentsPlugin.pending ?? ""
            FieldKeyIntentsPlugin.pending = nil
            call.resolve(["action": action])
        }
    }
}
