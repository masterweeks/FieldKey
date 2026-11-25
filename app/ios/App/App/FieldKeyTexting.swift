import UIKit
import Capacitor
import MessageUI

/// Texting without leaving FieldKey: Apple's message composer slides up over the app with the number
/// and message filled in, and iOS reports whether the text was sent, so FieldKey marks a site texted
/// only when it really was.
/// JS: Capacitor.nativePromise("FieldKeyTexting", "canText", {}) -> {value: Bool}
///     Capacitor.nativePromise("FieldKeyTexting", "compose", {to, body}) -> {result: "sent"|"cancelled"|"failed"}
/// The promise resolves after the composer has closed, so the next one can open straight away.
@objc(FieldKeyTextingPlugin)
public class FieldKeyTextingPlugin: CAPPlugin, CAPBridgedPlugin, MFMessageComposeViewControllerDelegate {
    public let identifier = "FieldKeyTextingPlugin"
    public let jsName = "FieldKeyTexting"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "canText", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "compose", returnType: CAPPluginReturnPromise)
    ]
    private var pending: CAPPluginCall?

    @objc func canText(_ call: CAPPluginCall) {
        DispatchQueue.main.async { call.resolve(["value": MFMessageComposeViewController.canSendText()]) }
    }

    @objc func compose(_ call: CAPPluginCall) {
        guard let to = call.getString("to"), !to.isEmpty else { call.reject("No number to text"); return }
        let body = call.getString("body") ?? ""
        DispatchQueue.main.async {
            guard MFMessageComposeViewController.canSendText() else {
                call.reject("This device can't send texts", "UNAVAILABLE")
                return
            }
            guard let host = self.bridge?.viewController else { call.reject("No screen to show the text on"); return }
            let composer = MFMessageComposeViewController()
            composer.recipients = [to]
            composer.body = body
            composer.messageComposeDelegate = self
            self.pending?.resolve(["result": "cancelled"])
            self.pending = call
            host.present(composer, animated: true)
        }
    }

    public func messageComposeViewController(_ controller: MFMessageComposeViewController, didFinishWith result: MessageComposeResult) {
        let outcome: String
        switch result {
        case .sent: outcome = "sent"
        case .failed: outcome = "failed"
        default: outcome = "cancelled"
        }
        controller.dismiss(animated: true) {
            self.pending?.resolve(["result": outcome])
            self.pending = nil
        }
    }
}
