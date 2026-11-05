import Foundation
import Testing
@testable import DincrCore

@Suite struct APIClientCacheTests {
    @Test func financialAnswersHaveNoDiskCache() {
        let configuration = URLSessionTransport.noCacheSession.configuration
        #expect(configuration.urlCache == nil)
        #expect(configuration.requestCachePolicy == .reloadIgnoringLocalCacheData)
        #expect(URLSessionTransport().session === URLSessionTransport.noCacheSession)
    }
}
