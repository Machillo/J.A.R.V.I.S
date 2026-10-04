import Foundation
import Testing
@testable import DincrCore

/// The four message kinds (DESIGN.md → Messages): a financial alert is never shown as a technical
/// error, progress is never shown as a problem, and an unknown severity is never downplayed.
/// Android checks the same mapping in `MessageKindTest.kt`.
@Suite struct MessageKindTests {
    @Test func everySeverityTheBackendSendsHasItsKind() {
        for severity in ["critical", "high", "medium"] {
            #expect(MessageKind.financial(severity: severity) == .attention, "\(severity)")
        }
        #expect(MessageKind.financial(severity: "success") == .positive)
    }

    @Test func aFinancialAlertIsNeverATechnicalError() {
        for severity in ["critical", "high", "medium", "low", "success", "blocking", "warning", "info", "error", "", "unexpected", nil] {
            #expect(MessageKind.financial(severity: severity) != .technicalError, "\(severity ?? "nil")")
        }
    }

    /// A problem is never downplayed to a suggestion: severities the alert screens don't receive
    /// today (`low`, `info`, data-quality `blocking`/`warning`) stay attention too.
    @Test func noSeverityIsDowngradedToASuggestion() {
        for severity in ["low", "info", "blocking", "warning", "error"] {
            #expect(MessageKind.financial(severity: severity) == .attention, "\(severity)")
        }
    }

    @Test func anUnknownOrMissingSeverityStaysVisibleAsAttention() {
        #expect(MessageKind.financial(severity: nil) == .attention)
        #expect(MessageKind.financial(severity: "") == .attention)
        #expect(MessageKind.financial(severity: "unexpected") == .attention)
        #expect(MessageKind.financial(severity: "HIGH") == .attention)
        #expect(MessageKind.financial(severity: "Success") == .positive)
    }

    /// Screens never pick a look from a raw severity: every financial severity goes through
    /// `MessageKind.financial`, so the same alert looks the same everywhere.
    @Test func screensMapSeveritiesOnlyThroughMessageKind() throws {
        // native/ios/DincrKit/Tests/DincrCoreTests/<this file> → native/ios/DINCR
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<4 { root.deleteLastPathComponent() }
        root.appendPathComponent("DINCR")
        let files = try #require(FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil))
            .compactMap { $0 as? URL }.filter { $0.pathExtension == "swift" }
        #expect(files.count > 20)
        var offenders: [String] = []
        for file in files {
            for (index, line) in try String(contentsOf: file, encoding: .utf8).components(separatedBy: "\n").enumerated()
            where line.contains("severity") && !line.contains(".financial(severity:") {
                offenders.append("\(file.lastPathComponent):\(index + 1)")
            }
        }
        #expect(offenders.isEmpty, "map severities with MessageKind.financial: \(offenders)")
    }
}
