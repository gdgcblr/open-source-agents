import Foundation
import EventKit
import Contacts

enum Failure: Error { case message(String) }

func waitPermission(_ request: (@escaping (Bool, Error?) -> Void) -> Void) throws {
    var done = false
    var allowed = false
    request { ok, _ in allowed = ok; done = true }
    let deadline = Date().addingTimeInterval(45)
    while !done && Date() < deadline {
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))
    }
    guard done && allowed else { throw Failure.message("App permission denied or timed out.") }
}

func execute(_ request: [String: Any]) throws -> Any {
    guard let op = request["operation"] as? String,
          let p = request["payload"] as? [String: Any] else {
        throw Failure.message("Invalid request.")
    }
    if op == "calendar.read" {
        let store = EKEventStore()
        if #available(macOS 14.0, *) {
            try waitPermission { store.requestFullAccessToEvents(completion: $0) }
        } else {
            try waitPermission { store.requestAccess(to: .event, completion: $0) }
        }
        let days = p["days"] as? Int ?? 14
        guard (1...90).contains(days) else { throw Failure.message("Invalid day limit.") }
        let start = Date()
        let end = Calendar.current.date(byAdding: .day, value: days, to: start)!
        let format = ISO8601DateFormatter()
        return store.events(matching: store.predicateForEvents(withStart: start, end: end,
                                                              calendars: nil))
            .sorted { $0.startDate < $1.startDate }.prefix(500).map { event in
                ["id": event.eventIdentifier ?? "", "title": event.title ?? "",
                 "start": format.string(from: event.startDate),
                 "end": format.string(from: event.endDate), "all_day": event.isAllDay,
                 "calendar": event.calendar.title] as [String: Any]
            }
    }
    guard op == "contacts.search" || op == "contacts.save" else {
        throw Failure.message("Operation is not permitted.")
    }
    let store = CNContactStore()
    try waitPermission { store.requestAccess(for: .contacts, completionHandler: $0) }
    let keys = [CNContactIdentifierKey, CNContactGivenNameKey, CNContactFamilyNameKey,
                CNContactEmailAddressesKey, CNContactBirthdayKey, CNContactDatesKey]
        .map { $0 as CNKeyDescriptor }
    if op == "contacts.search" {
        let query = p["query"] as? String ?? ""
        guard !query.isEmpty && query.count <= 100 else { throw Failure.message("Invalid query.") }
        return try store.unifiedContacts(matching: CNContact.predicateForContacts(matchingName: query),
                                         keysToFetch: keys).prefix(50).map { c in
            var result: [String: Any] = ["id": c.identifier, "given_name": c.givenName,
                "family_name": c.familyName, "emails": c.emailAddresses.map { String($0.value) }]
            if let b = c.birthday {
                result["birthday"] = ["month": b.month ?? 0, "day": b.day ?? 0]
            }
            result["dates"] = c.dates.map { value in
                ["label": value.label ?? "", "month": value.value.month,
                 "day": value.value.day] as [String: Any]
            }
            return result
        }
    }
    let id = p["id"] as? String ?? ""
    let contact: CNMutableContact
    if id.isEmpty { contact = CNMutableContact() }
    else {
        contact = try store.unifiedContact(withIdentifier: id, keysToFetch: keys)
            .mutableCopy() as! CNMutableContact
    }
    guard let given = p["given_name"] as? String, !given.isEmpty else {
        throw Failure.message("Given name is required.")
    }
    contact.givenName = given
    contact.familyName = p["family_name"] as? String ?? ""
    let email = p["email"] as? String ?? ""
    // Append a new email; preserve existing addresses and other contact fields.
    if !email.isEmpty && !contact.emailAddresses.contains(where: { String($0.value) == email }) {
        contact.emailAddresses.append(CNLabeledValue(label: CNLabelHome, value: email as NSString))
    }
    let save = CNSaveRequest()
    if id.isEmpty { save.add(contact, toContainerWithIdentifier: nil) }
    else { save.update(contact) }
    try store.execute(save)
    return ["id": contact.identifier, "changed": true]
}

do {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    guard data.count <= 8192,
          let request = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        throw Failure.message("Invalid input.")
    }
    let result = try execute(request)
    let output = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    FileHandle.standardOutput.write(output)
} catch {
    FileHandle.standardError.write(Data("Mac app operation failed: \(error)\n".utf8))
    exit(1)
}
