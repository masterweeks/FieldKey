import Foundation
import Capacitor

/// "Open in FieldKey" for KML, KMZ and CSV files (the document types in Info.plist): from Files,
/// Mail, Safari downloads or the share sheet. SceneDelegate hands each file here; the page collects
/// it with Capacitor.nativePromise("FieldKeyFiles", "takePending", {}) -> {name, data (base64)} on
/// start, when it comes back to the front, and on the window event "fieldkeyfile", then runs it
/// through the usual import (openImport() in index.html).
@objc(FieldKeyFilesPlugin)
public class FieldKeyFilesPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "FieldKeyFilesPlugin"
    public let jsName = "FieldKeyFiles"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "takePending", returnType: CAPPluginReturnPromise)
    ]

    private static var pending: (name: String, data: Data)?
    private static weak var current: FieldKeyFilesPlugin?

    override public func load() {
        FieldKeyFilesPlugin.current = self
    }

    /// Keeps the file the user opened (the last one, if several) and nudges the page if it's running.
    /// Returns false for anything that isn't a readable file.
    @discardableResult
    static func receive(_ url: URL) -> Bool {
        guard url.isFileURL else { return false }
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        guard let data = try? Data(contentsOf: url) else { return false }
        pending = (url.lastPathComponent, data)
        DispatchQueue.main.async {
            current?.bridge?.triggerWindowJSEvent(eventName: "fieldkeyfile")
        }
        return true
    }

    @objc func takePending(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            guard let file = FieldKeyFilesPlugin.pending else { call.resolve(["name": ""]); return }
            FieldKeyFilesPlugin.pending = nil
            call.resolve(["name": file.name, "data": file.data.base64EncodedString()])
        }
    }
}
