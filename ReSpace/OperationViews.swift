import SwiftUI

struct OperationPanel: View {
    let app: AppModel
    @Binding var operation: JSONValue
    var roomDocument: JSONValue = .null
    let onUpdate: () async -> Void
    @State private var choices: Set<String> = []
    @State private var text = ""
    @State private var number: Double?
    @State private var revisionAnswer: JSONValue = .null
    @State private var error: String?
    @State private var busy = false
    @State private var options = false
    @State private var cancelling = false
    @State private var selectedObject: String?
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var question: JSONValue { revisionAnswer == .null ? operation["pending_question"] : revisionAnswer["question"] }
    var revising: Bool { revisionAnswer != .null }
    var formIdentity: String { revising ? revisionAnswer["answer_id"].text : question["question_id"].text }
    var numeric: NumericQuestion { NumericQuestion(question) }
    var displayedNumber: Double { number ?? numeric.initialValue }
    private var terminal: Bool { ["succeeded", "failed", "cancelled", "rejected"].contains(operation["state"].text) }
    private var singleChoice: Bool { question["max_selections"].int == 1 && !["numeric", "text", "budget"].contains(question["kind"].text) }
    private var title: String {
        if cancelling { return "Cancel this request?" }
        if options { return "Your question" }
        if question != .null { return question["text"].text }
        switch operation["state"].text {
        case "succeeded": return operation["outcome"]["result_kind"].text == "selection" ? "Your plan is ready." : operation["kind"].text == "generation" ? "Your room is ready." : "Changes saved."
        case "failed", "rejected": return "Let’s take another look."
        case "cancelled": return "Request cancelled."
        default: return ["preparing", "preparing_context", "planning", "discovering", "searching", "searching_products", "interview"].contains(operation["phase"].text) ? "Getting to know\nyour room." : "Designing your room."
        }
    }
    var body: some View {
        ZStack {
        RSPage(title: title, question: question != .null || cancelling, back: { if options || cancelling { options = false; cancelling = false } else { dismiss() } },
               trailingSymbol: question != .null ? "ellipsis" : "xmark", trailingLabel: question != .null ? "Question options" : "Leave for now",
               trailing: options || cancelling ? nil : { if question != .null { options = true } else { dismiss() } }) {
            if cancelling {
                RSSymbol(name: "xmark")
                Text("Further work will stop. Your room and earlier saved designs stay available.").foregroundStyle(ReSpaceStyle.secondary)
            } else if options { questionOptions }
            else if question != .null {
                questionContent
            } else { operationContent }
            if let error { RSNotice(message: error, isError: true) }
        } footer: { footer }
        .id(formIdentity)
        .transition(reduceMotion ? .identity : .asymmetric(insertion: .offset(y: 240).combined(with: .scale(scale: 0.94)).combined(with: .opacity), removal: .offset(y: -145).combined(with: .scale(scale: 0.96)).combined(with: .opacity)))
        }.background(.white).clipped()
        .animation(reduceMotion ? nil : .timingCurve(0.16, 1, 0.3, 1, duration: 0.62), value: formIdentity)
        .onChange(of: formIdentity) { _, _ in
            choices = Set(revisionAnswer["request"]["choice_ids"].array.compactMap(\.string))
            text = revisionAnswer["request"]["text"].text
            number = revisionAnswer["request"]["number"].number
        }
        .onChange(of: operation["answer_revision_allowed"].bool) { _, allowed in if allowed != true { revisionAnswer = .null } }
    }
    @ViewBuilder private var questionContent: some View {
        if revising { Button("Keep current answer") { revisionAnswer = .null }.buttonStyle(RSButtonStyle(kind: .secondary)) }
        if question["kind"].text == "budget" {
            VStack(spacing: 0) {
                RSKeyValue(title: "Current limit", value: "USD \(question["budget_proposal"]["old_ceiling"].text)")
                RSKeyValue(title: "Proposed limit", value: "USD \(question["budget_proposal"]["new_ceiling"].text)")
                RSKeyValue(title: "New purchase total", value: "USD \(question["budget_proposal"]["resulting_total"].text)")
            }
            Text("Tax & shipping extra.").font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
        }
        VStack(spacing: 16) {
            ForEach(question["choices"].array, id: \.self) { choice in
                if let url = URL(string: choice["image_url"].text), !choice["image_url"].text.isEmpty {
                    Button { choose(choice) } label: {
                        HStack(spacing: 16) {
                            AsyncImage(url: url) { $0.resizable().scaledToFit() } placeholder: { ProgressView() }.frame(width: 96, height: 120).background(ReSpaceStyle.canvas, in: RoundedRectangle(cornerRadius: 16))
                            VStack(alignment: .leading, spacing: 8) {
                                Text(choice["label"].text).font(ReSpaceStyle.font(16, weight: .medium))
                                if choice["listing"] != .null {
                                    let listing = choice["listing"]
                                    Text("$\(productPrice(listing)) · \(productOffer(listing)["merchant"].text)").font(ReSpaceStyle.font(13))
                                    Text(listing["dimensions"].numbers.map { String(format: "%.1f", $0 * 100) }.joined(separator: " × ") + " cm")
                                        .font(ReSpaceStyle.font(12))
                                    Text("Offer checked \(displayDate(productOffer(listing)["checked_at"].text)) · fit pending").font(ReSpaceStyle.font(12))
                                }
                                if let description = choice["description"].string { Text(description).font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary) }
                            }.frame(maxWidth: .infinity, alignment: .leading)
                            if choices.contains(choice["choice_id"].text) { Image(systemName: "checkmark.circle.fill").foregroundStyle(ReSpaceStyle.purple) }
                        }.padding(12).background(choices.contains(choice["choice_id"].text) ? ReSpaceStyle.wash : .white, in: RoundedRectangle(cornerRadius: 20))
                            .overlay { RoundedRectangle(cornerRadius: 20).stroke(ReSpaceStyle.line, lineWidth: 1) }
                    }.buttonStyle(.plain).disabled(busy)
                } else {
                    RSChoice(title: choice["label"].text, subtitle: choice["listing"] == .null ? "" : "$\(productPrice(choice["listing"])) · \(choice["listing"]["dimensions"].numbers.map { String(format: "%.1f", $0 * 100) }.joined(separator: " × ")) cm · fit pending", selected: choices.contains(choice["choice_id"].text)) { choose(choice) }.disabled(busy)
                }
            }
        }
        if question["kind"].text == "numeric" {
            Stepper("\(displayedNumber.formatted())", onIncrement: numeric.next(displayedNumber, direction: 1).map { value in { number = value } }, onDecrement: numeric.next(displayedNumber, direction: -1).map { value in { number = value } })
                .font(ReSpaceStyle.font(32, weight: .medium)).padding(24).background(ReSpaceStyle.wash, in: RoundedRectangle(cornerRadius: 20)).disabled(busy).accessibilityLabel(question["text"].text)
        }
        if question["kind"].text == "text" {
            TextField("Your answer", text: $text, axis: .vertical).lineLimit(5...8).rsInput()
        } else if question["kind"].text != "budget" {
            DisclosureGroup("Add details") { TextField("Optional details", text: $text, axis: .vertical).lineLimit(2...5).rsInput().padding(.top, 12) }
                .font(ReSpaceStyle.font(13)).foregroundStyle(ReSpaceStyle.secondary)
        }
    }
    private func choose(_ choice: JSONValue) {
        let id = choice["choice_id"].text
        if question["max_selections"].int <= 1 { choices = [id] }
        else if choices.contains(id) { choices.remove(id) }
        else if choices.count < question["max_selections"].int { choices.insert(id) }
        if singleChoice && !revising { Task { await answer("answer") } }
    }
    @ViewBuilder private var questionOptions: some View {
        VStack(spacing: 0) {
            if question["allow_delegate"].bool == true {
                Button { options = false; Task { await answer("delegate") } } label: { RSRow(title: "Decide for me", subtitle: "Within your budget and protected choices", symbol: "checkmark") }.disabled(busy)
            }
            Button { dismiss() } label: { RSRow(title: "Leave for now", subtitle: "Your question will be here when you return", symbol: "xmark") }
            if !terminal { Button { options = false; cancelling = true } label: { RSRow(title: "Cancel this request", symbol: "trash") }.disabled(busy) }
            if question["context"].text == "command" {
                Button { Task { await control("dismiss-clarification", extra: ["question_id": question["question_id"], "dismissal_id": .string(UUID().uuidString)]); options = false } } label: { RSRow(title: "Dismiss clarification", subtitle: "Leave the room unchanged", symbol: "bubble.left") }.disabled(busy)
            }
        }.buttonStyle(.plain)
        if !operation["answer_history"].array.isEmpty {
            DisclosureGroup("Earlier questions and answers") {
                ForEach(operation["answer_history"].array, id: \.self) { entry in
                    VStack(alignment: .leading, spacing: 12) {
                        Text(entry["question"]["text"].text).font(ReSpaceStyle.font(16, weight: .medium))
                        Text(AnswerHistory.summary(entry)).font(ReSpaceStyle.font(14)).foregroundStyle(ReSpaceStyle.secondary)
                        if entry["request"]["revision_of_answer_id"].string != nil { Text("Revised answer · earlier response retained").font(ReSpaceStyle.font(12)) }
                        Button("Revise this answer") { revisionAnswer = entry; options = false }.buttonStyle(RSButtonStyle(kind: .secondary)).disabled(busy || operation["answer_revision_allowed"].bool != true)
                    }.padding(.vertical, 12)
                }
                if operation["answer_revision_allowed"].bool != true { Text("Answers can be revised when planning pauses at an interview question.").font(ReSpaceStyle.font(13)) }
            }
        }
    }
    @ViewBuilder private var operationContent: some View {
        if roomDocument != .null && !terminal {
            RoomScene(document: roomDocument, native: true, selectedID: $selectedObject, ghosts: true, resetToken: 0)
                .frame(height: 250).clipShape(RoundedRectangle(cornerRadius: 28))
        } else { RSSymbol(name: terminal ? (operation["state"].text == "succeeded" ? "checkmark" : "arrow.clockwise") : "sparkles") }
        if !terminal {
            HStack(spacing: 12) { ProgressView(); Text(operation["progress_message"].string ?? operation["phase"].text.replacingOccurrences(of: "_", with: " ").capitalized).font(ReSpaceStyle.font(14)).fixedSize(horizontal: false, vertical: true) }.padding(.vertical, 12)
        }
        ForEach(operation["outcome"]["action_outcomes"].array, id: \.self) { action in
            RSNotice(message: "\(action["type"].text.capitalized): \(action["outcome"].text.replacingOccurrences(of: "_", with: " ")) · \(action["reason"].text)", isError: action["outcome"].text == "failed")
        }
        if let message = operation["outcome"]["message"].string { Text(message) }
        ForEach(operation["outcome"]["warnings"].array, id: \.self) { RSNotice(message: $0["message"].text) }
        if let failure = operation["failure"]["message"].string { RSNotice(message: failure, isError: true) }
        if operation["outcome"]["result_kind"].text == "selection" {
            Text("Verified Product selection · spatial fit pending").font(ReSpaceStyle.font(18, weight: .semibold))
            ForEach(operation["controller"]["selection"]["selected"].array, id: \.self) { product in
                ProductSummary(product: product)
                NavigationLink("Evidence and scores") { OptionEvidence(choice: product) }
            }
            RSKeyValue(title: "Purchase total", value: "USD \(operation["controller"]["selection"]["purchases"]["total"].text)")
        }
    }
    @ViewBuilder private var footer: some View {
        if cancelling {
            Button("Keep going") { cancelling = false }.buttonStyle(RSButtonStyle())
            Button("Cancel request") { Task { await control("cancel", extra: ["cancellation_id": .string(UUID().uuidString)]); cancelling = false } }.buttonStyle(RSButtonStyle(kind: .quiet)).disabled(busy)
        } else if options {
            Button("Back to question") { options = false }.buttonStyle(RSButtonStyle(kind: .secondary))
        } else if question != .null {
            if question["kind"].text == "budget" {
                Button("Approve USD \(question["budget_proposal"]["new_ceiling"].text) limit") { Task { await answer("answer", approve: true) } }.buttonStyle(RSButtonStyle()).disabled(busy)
            } else if !singleChoice || revising {
                Button(busy ? "Saving…" : revising ? "Save revised answer" : "Continue") { Task { await answer("answer") } }.buttonStyle(RSButtonStyle()).disabled(busy || !validAnswer)
            }
            if busy { ProgressView().accessibilityLabel("Saving your answer") }
            if question["allow_skip"].bool == true { Button("Skip this question") { Task { await answer("skip") } }.buttonStyle(RSButtonStyle(kind: .quiet)).disabled(busy) }
        } else {
            if terminal {
                if operation["state"].text == "succeeded", operation["kind"].text == "generation", let designID = operation["outcome"]["design_id"].string {
                    NavigationLink { DesignView(app: app, roomID: operation["room_id"].text, designID: designID) } label: { Text("Explore your room") }.buttonStyle(RSButtonStyle())
                    Button("Back to room") { dismiss() }.buttonStyle(RSButtonStyle(kind: .quiet))
                } else { Button("Back to room") { dismiss() }.buttonStyle(RSButtonStyle()) }
                if operation["state"].text != "succeeded" { Button("Check request") { Task { await refresh() } }.buttonStyle(RSButtonStyle(kind: .secondary)) }
            } else {
                Button("Leave for now") { dismiss() }.buttonStyle(RSButtonStyle(kind: .quiet))
                Button("Cancel request") { cancelling = true }.buttonStyle(RSButtonStyle(kind: .quiet)).disabled(busy)
            }
        }
    }
    var validAnswer: Bool {
        if question["kind"].text == "numeric" { return numeric.isValid(displayedNumber) }
        if question["kind"].text == "text" { return !text.isEmpty }
        return choices.count >= question["min_selections"].int && choices.count <= question["max_selections"].int
    }
    func refresh() async { guard let client = app.client else { return }; do { operation = try await client.request("operations/\(operation["operation_id"].text)")["operation"]; await onUpdate() } catch { self.error = error.localizedDescription } }
    func answer(_ action: String, approve: Bool = false) async {
        var body: [String: JSONValue] = ["question_id": question["question_id"], "reply_id": .string(UUID().uuidString), "expected_decision_revision": operation["decision_revision"], "expected_question_revision": question["question_revision"], "choice_ids": .array(choices.sorted().map(JSONValue.string)), "text": .string(text), "action": .string(action)]
        if revising {
            do { body.merge(try AnswerHistory.revisionIdentity(answerID: revisionAnswer["answer_id"].text, operation: operation)) { _, current in current } }
            catch { self.error = error.localizedDescription; return }
        }
        if question["kind"].text == "numeric", action == "answer" { body["number"] = .number(displayedNumber) }
        if approve { body["budget_approval"] = .object(["old_ceiling": question["budget_proposal"]["old_ceiling"], "new_ceiling": question["budget_proposal"]["new_ceiling"], "resulting_total": question["budget_proposal"]["resulting_total"]]) }
        await control("answers", extra: body)
    }
    func control(_ action: String, extra: [String: JSONValue]) async {
        busy = true; defer { busy = false }
        do {
            var body = extra; body["operation_id"] = operation["operation_id"]
            let request = PendingRequest(path: "operations/\(operation["operation_id"].text)/\(action)", roomID: operation["room_id"].text, body: body)
            operation = try await app.submit(request)["operation"]; if action == "answers" { revisionAnswer = .null }; await onUpdate()
        } catch { self.error = error.localizedDescription }
    }
}

#if DEBUG
#Preview("Question") { UIDemoPreview(.question) }
#Preview("Generating") { UIDemoPreview(.generating) }
#Preview("Ready") { UIDemoPreview(.ready) }
#endif
