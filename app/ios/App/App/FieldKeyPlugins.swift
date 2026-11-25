import UIKit
import Capacitor
import EventKit
import EventKitUI

/// The app's main screen (Main.storyboard): Capacitor's web view, plus FieldKey's own native plugins.
class FieldKeyViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(FieldKeyCalendarPlugin())
        bridge?.registerPluginInstance(FieldKeyTextingPlugin())   // FieldKeyTexting.swift
        bridge?.registerPluginInstance(FieldKeyLiveActivityPlugin())   // FieldKeyLiveActivity.swift
        bridge?.registerPluginInstance(FieldKeyIntentsPlugin())   // FieldKeyIntents.swift
        bridge?.registerPluginInstance(FieldKeyAIPlugin())   // FieldKeyAI.swift
        bridge?.registerPluginInstance(FieldKeyCarPlayPlugin())   // FieldKeyCarPlay.swift
    }
}

/// "Apple Calendar" on a scheduled site: opens Apple's own New Event screen, filled in, where the
/// user taps Add. On iOS 17 and later that screen needs no calendar permission; on iOS 15-16 the
/// app asks first (NSCalendarsUsageDescription in Info.plist).
/// JS: Capacitor.nativePromise("FieldKeyCalendar", "addEvent", {title, location, notes, start, end})
/// with start and end in milliseconds; resolves {added: true|false}.
@objc(FieldKeyCalendarPlugin)
public class FieldKeyCalendarPlugin: CAPPlugin, CAPBridgedPlugin, EKEventEditViewDelegate {
    public let identifier = "FieldKeyCalendarPlugin"
    public let jsName = "FieldKeyCalendar"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "addEvent", returnType: CAPPluginReturnPromise)
    ]
    private let store = EKEventStore()
    private var pending: CAPPluginCall?

    @objc func addEvent(_ call: CAPPluginCall) {
        guard let start = call.getDouble("start"), let end = call.getDouble("end") else {
            call.reject("Missing start or end time")
            return
        }
        let show = { DispatchQueue.main.async { self.present(call, start: start, end: end) } }
        if #available(iOS 17.0, *) {
            show()
        } else {
            store.requestAccess(to: .event) { granted, _ in
                if granted { show() } else { call.reject("Calendar access is off. Allow it in Settings → FieldKey.") }
            }
        }
    }

    private func present(_ call: CAPPluginCall, start: Double, end: Double) {
        guard let host = bridge?.viewController else { call.reject("No screen to show the event on"); return }
        let event = EKEvent(eventStore: store)
        event.title = call.getString("title") ?? "Inspection"
        event.location = call.getString("location")
        event.notes = call.getString("notes")
        event.startDate = Date(timeIntervalSince1970: start / 1000)
        event.endDate = Date(timeIntervalSince1970: end / 1000)
        if #unavailable(iOS 17.0) { event.calendar = store.defaultCalendarForNewEvents }
        let editor = EKEventEditViewController()
        editor.eventStore = store
        editor.event = event
        editor.editViewDelegate = self
        pending?.resolve(["added": false])
        pending = call
        host.present(editor, animated: true)
    }

    public func eventEditViewController(_ controller: EKEventEditViewController, didCompleteWith action: EKEventEditViewAction) {
        controller.dismiss(animated: true)
        pending?.resolve(["added": action == .saved])
        pending = nil
    }
}
