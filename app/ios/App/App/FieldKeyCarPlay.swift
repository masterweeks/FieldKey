import Foundation
import UIKit
import Capacitor
import CarPlay

/// The CarPlay app: today's scheduled sites as a list; each opens a card with the time, access
/// notes and address, and Call and Directions buttons.
///
/// It only appears in the car once Apple grants the CarPlay driving-task entitlement (see
/// docs/ios-app.md, "CarPlay entitlement"). Until then the entitlement is only in simulator builds
/// (App/FieldKeySimulator.entitlements), so it can be tried with Simulator → I/O → External
/// Displays → CarPlay, and phone builds sign as before.
///
/// The page sends today's list whenever it changes (refreshRouteLive() in index.html):
///   Capacitor.nativePromise("FieldKeyCarPlay", "setSites", {sites: [{name, time, address,
///     access, notes, phone, lat, lng, done}]})
/// It's kept in UserDefaults, so CarPlay can show the last list even when FieldKey was started
/// from the car and the page isn't running.
@objc(FieldKeyCarPlayPlugin)
public class FieldKeyCarPlayPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "FieldKeyCarPlayPlugin"
    public let jsName = "FieldKeyCarPlay"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "setSites", returnType: CAPPluginReturnPromise)
    ]

    @objc func setSites(_ call: CAPPluginCall) {
        let raw = call.getArray("sites", JSObject.self) ?? []
        let sites = raw.map(CarPlaySite.init)
        CarPlaySite.save(sites)
        call.resolve()
    }
}

struct CarPlaySite: Codable {
    var name: String
    var time: String
    var address: String
    var access: String
    var notes: String
    var phone: String
    var lat: Double?
    var lng: Double?
    var done: Bool

    init(_ o: JSObject) {
        name = o["name"] as? String ?? ""
        time = o["time"] as? String ?? ""
        address = o["address"] as? String ?? ""
        access = o["access"] as? String ?? ""
        notes = o["notes"] as? String ?? ""
        phone = o["phone"] as? String ?? ""
        lat = (o["lat"] as? NSNumber)?.doubleValue
        lng = (o["lng"] as? NSNumber)?.doubleValue
        done = o["done"] as? Bool ?? false
    }

    static let key = "fk_carplay_sites"
    static let changed = Notification.Name("FieldKeyCarPlaySitesChanged")

    static func save(_ sites: [CarPlaySite]) {
        let day = Calendar.current.startOfDay(for: Date()).timeIntervalSince1970
        if let data = try? JSONEncoder().encode(sites) {
            UserDefaults.standard.set(data, forKey: key)
            UserDefaults.standard.set(day, forKey: key + "_day")
        }
        DispatchQueue.main.async { NotificationCenter.default.post(name: changed, object: nil) }
    }

    /// The saved list, or nothing if it was saved on another day.
    static func load() -> [CarPlaySite] {
        let day = Calendar.current.startOfDay(for: Date()).timeIntervalSince1970
        guard UserDefaults.standard.double(forKey: key + "_day") == day,
              let data = UserDefaults.standard.data(forKey: key),
              let sites = try? JSONDecoder().decode([CarPlaySite].self, from: data) else { return [] }
        return sites
    }
}

class CarPlaySceneDelegate: UIResponder, CPTemplateApplicationSceneDelegate {
    private var interfaceController: CPInterfaceController?
    private weak var scene: CPTemplateApplicationScene?
    private let list = CPListTemplate(title: "Today", sections: [])

    func templateApplicationScene(_ templateApplicationScene: CPTemplateApplicationScene,
                                  didConnect interfaceController: CPInterfaceController) {
        self.interfaceController = interfaceController
        self.scene = templateApplicationScene
        list.emptyViewTitleVariants = ["No sites today"]
        list.emptyViewSubtitleVariants = ["Sites scheduled for today in FieldKey appear here."]
        reload()
        interfaceController.setRootTemplate(list, animated: false, completion: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(reload),
                                               name: CarPlaySite.changed, object: nil)
    }

    func templateApplicationScene(_ templateApplicationScene: CPTemplateApplicationScene,
                                  didDisconnectInterfaceController interfaceController: CPInterfaceController) {
        NotificationCenter.default.removeObserver(self)
        self.interfaceController = nil
    }

    @objc private func reload() {
        let sites = CarPlaySite.load()
        let next = sites.firstIndex { !$0.done }
        let items: [CPListItem] = sites.enumerated().map { i, s in
            let detail = [s.time, s.done ? "Done" : (i == next ? "Next" : ""), s.access]
                .filter { !$0.isEmpty }.joined(separator: " · ")
            let item = CPListItem(text: s.name, detailText: detail,
                                  image: UIImage(systemName: s.done ? "checkmark.circle.fill" : "mappin.circle.fill"))
            item.handler = { [weak self] _, done in
                self?.show(s)
                done()
            }
            return item
        }
        let left = sites.filter { !$0.done }.count
        let header = sites.isEmpty ? nil : "\(left) of \(sites.count) left"
        list.updateSections([CPListSection(items: items, header: header, sectionIndexTitle: nil)])
    }

    private func show(_ s: CarPlaySite) {
        var items: [CPInformationItem] = []
        if !s.time.isEmpty { items.append(CPInformationItem(title: "Time", detail: s.time)) }
        if !s.access.isEmpty { items.append(CPInformationItem(title: "Access", detail: s.access)) }
        if !s.notes.isEmpty { items.append(CPInformationItem(title: "Notes", detail: s.notes)) }
        if !s.address.isEmpty { items.append(CPInformationItem(title: "Address", detail: s.address)) }

        var actions: [CPTextButton] = []
        if let url = Self.directions(s) {
            actions.append(CPTextButton(title: "Directions", textStyle: .confirm) { [weak self] _ in
                self?.scene?.open(url, options: nil, completionHandler: nil)
            })
        }
        let digits = s.phone.filter { $0.isNumber || $0 == "+" }
        if !digits.isEmpty, let url = URL(string: "tel:" + digits) {
            actions.append(CPTextButton(title: "Call", textStyle: .normal) { [weak self] _ in
                self?.scene?.open(url, options: nil, completionHandler: nil)
            })
        }
        let card = CPInformationTemplate(title: s.name, layout: .twoColumn, items: items, actions: actions)
        interfaceController?.pushTemplate(card, animated: true, completion: nil)
    }

    /// Apple Maps driving directions, to the site's pin if it has one, else its address.
    static func directions(_ s: CarPlaySite) -> URL? {
        var c = URLComponents(string: "maps://")!
        if let lat = s.lat, let lng = s.lng {
            c.queryItems = [URLQueryItem(name: "daddr", value: "\(lat),\(lng)"), URLQueryItem(name: "dirflg", value: "d")]
        } else if !s.address.isEmpty {
            c.queryItems = [URLQueryItem(name: "daddr", value: s.address), URLQueryItem(name: "dirflg", value: "d")]
        } else {
            return nil
        }
        return c.url
    }
}
