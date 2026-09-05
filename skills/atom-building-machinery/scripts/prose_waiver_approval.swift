import AppKit
import CryptoKit
import Foundation
import LocalAuthentication
import Security

let contractVersion = 1
let helperVersion = 1
let service = "memory-knowledge.atom-building.prose-waiver.native-v1"
let account = NSUserName()
let meanings = [
    "waive": "I authorize this exact validation request to start as a recorded prose exception. This does not authorize promotion, operational use, another field, or another atom.",
    "decline": "I do not authorize this request to start while it reads prose. It must use a structured field before proceeding.",
]
let harnessMarkers = [
    "CLAUDECODE",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_PID",
    "CODEX_APP_TOOLS_PIPE_PATH",
    "CODEX_CI",
    "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
    "CODEX_MCP_NODE_PATH",
    "CODEX_PERMISSION_PROFILE",
    "CODEX_SAGE_BACKFILL_TRACKER_TAB_REUSE",
    "CODEX_SANDBOX_NETWORK_DISABLED",
    "CODEX_SESSION_ID",
    "CODEX_SHELL",
    "CODEX_THREAD_ID",
]

func fail(_ stage: String, _ message: String) -> Never {
    let output = try! JSONSerialization.data(
        withJSONObject: ["schema_version": contractVersion, "status": "refused", "stage": stage, "reason": message],
        options: [.sortedKeys]
    )
    FileHandle.standardError.write(output)
    FileHandle.standardError.write(Data("\n".utf8))
    exit(2)
}

func securityError(_ status: OSStatus) -> String {
    SecCopyErrorMessageString(status, nil) as String? ?? "OSStatus \(status)"
}

func hex(_ data: Data) -> String {
    data.map { String(format: "%02x", $0) }.joined()
}

func sha256(_ data: Data) -> String {
    hex(Data(SHA256.hash(data: data)))
}

func randomHex(byteCount: Int) -> String {
    var generated = Data(count: byteCount)
    let status = generated.withUnsafeMutableBytes { bytes in
        SecRandomCopyBytes(kSecRandomDefault, byteCount, bytes.baseAddress!)
    }
    guard status == errSecSuccess else {
        fail("authorize", "secure random generation failed: \(securityError(status))")
    }
    return hex(generated)
}

func installedHelpers() -> [(String, String)] {
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    return [
        ("codex", "\(home)/.codex/skills/atom-building-machinery/scripts/prose_waiver_approval"),
        ("claude", "\(home)/.claude/skills/atom-building-machinery/scripts/prose_waiver_approval"),
    ]
}

func resolved(_ path: String) -> String {
    URL(fileURLWithPath: path).standardizedFileURL.resolvingSymlinksInPath().path
}

func validatedInstallation(stage: String) -> (projection: String, helperPath: String, helperSHA256: String) {
    let current = resolved(CommandLine.arguments[0])
    let expected = installedHelpers()
    guard let projection = expected.first(where: { resolved($0.1) == current })?.0 else {
        fail(stage, "approval helper ran from \(current); run the managed installer for both clients and invoke the installed skill")
    }
    var observedHashes: [String] = []
    for (_, path) in expected {
        let url = URL(fileURLWithPath: path)
        guard let data = try? Data(contentsOf: url) else {
            fail(stage, "managed approval helper is missing at \(path); refresh both Codex and Claude projections")
        }
        observedHashes.append(sha256(data))
    }
    guard Set(observedHashes).count == 1 else {
        fail(stage, "Codex and Claude approval helpers differ; refresh both projections through the managed installer")
    }
    return (projection, current, observedHashes[0])
}

func exactObject(_ value: Any, keys: Set<String>, stage: String, label: String) -> [String: Any] {
    guard let object = value as? [String: Any], Set(object.keys) == keys else {
        fail(stage, "\(label) must contain exactly \(Array(keys).sorted())")
    }
    return object
}

func inputObject(stage: String) -> [String: Any] {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    guard !data.isEmpty else { fail(stage, "authorization context is empty") }
    let decoded: Any
    do {
        decoded = try JSONSerialization.jsonObject(with: data)
    } catch {
        fail(stage, "authorization context is not JSON: \(error.localizedDescription)")
    }
    let object = exactObject(
        decoded,
        keys: ["schema_version", "request_sha256", "repository_root", "fields"],
        stage: stage,
        label: "authorization context"
    )
    guard object["schema_version"] as? Int == contractVersion else {
        fail(stage, "authorization context schema_version must be \(contractVersion)")
    }
    guard let requestSHA = object["request_sha256"] as? String,
          requestSHA.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil else {
        fail(stage, "authorization context request_sha256 must be lowercase SHA-256")
    }
    guard let repositoryRoot = object["repository_root"] as? String,
          repositoryRoot.hasPrefix("/") else {
        fail(stage, "authorization context repository_root must be absolute")
    }
    guard let fields = object["fields"] as? [String], !fields.isEmpty,
          Set(fields).count == fields.count, fields.allSatisfy({ !$0.isEmpty }) else {
        fail(stage, "authorization context fields must be unique non-empty strings")
    }
    return object
}

func secret(createIfMissing: Bool, stage: String) -> Data {
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: service,
        kSecAttrAccount as String: account,
        kSecMatchLimit as String: kSecMatchLimitOne,
        kSecReturnData as String: true,
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecSuccess, let data = result as? Data { return data }
    if status != errSecItemNotFound || !createIfMissing {
        fail(stage, "protected approval key is unavailable: \(securityError(status)); refresh both managed projections and authorize again")
    }
    var generated = Data(count: 32)
    let randomStatus = generated.withUnsafeMutableBytes { bytes in
        SecRandomCopyBytes(kSecRandomDefault, 32, bytes.baseAddress!)
    }
    guard randomStatus == errSecSuccess else {
        fail(stage, "protected approval key generation failed: \(securityError(randomStatus))")
    }
    var trusted: [SecTrustedApplication] = []
    for (_, path) in installedHelpers() {
        var application: SecTrustedApplication?
        let appStatus = SecTrustedApplicationCreateFromPath(path, &application)
        guard appStatus == errSecSuccess, let application else {
            fail(stage, "could not bind protected approval key to \(path): \(securityError(appStatus))")
        }
        trusted.append(application)
    }
    var access: SecAccess?
    let accessStatus = SecAccessCreate(
        "Atom Building Machinery prose-waiver proof" as CFString,
        trusted as CFArray,
        &access
    )
    guard accessStatus == errSecSuccess, let access else {
        fail(stage, "protected approval-key access could not be created: \(securityError(accessStatus))")
    }
    let add: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: service,
        kSecAttrAccount as String: account,
        kSecAttrLabel as String: "Atom Building Machinery prose-waiver proof",
        kSecAttrDescription as String: "Used only by the installed Codex and Claude approval helpers",
        kSecAttrAccess as String: access,
        kSecValueData as String: generated,
    ]
    let addStatus = SecItemAdd(add as CFDictionary, nil)
    guard addStatus == errSecSuccess else {
        fail(stage, "protected approval key could not be stored: \(securityError(addStatus))")
    }
    return generated
}

func authenticate(choice: String) {
    let context = LAContext()
    let policy = LAPolicy.deviceOwnerAuthentication
    var availabilityError: NSError?
    guard context.canEvaluatePolicy(policy, error: &availabilityError) else {
        fail("authorize", "macOS authentication is unavailable: \(availabilityError?.localizedDescription ?? "unknown")")
    }
    let semaphore = DispatchSemaphore(value: 0)
    var accepted = false
    var failure: Error?
    context.evaluatePolicy(
        policy,
        localizedReason: "Confirm your \(choice) choice for this exact atom request"
    ) { ok, error in
        accepted = ok
        failure = error
        semaphore.signal()
    }
    semaphore.wait()
    guard accepted else {
        fail("authorize", "macOS authentication did not confirm the decision: \(failure?.localizedDescription ?? "unknown")")
    }
}

func authenticatedDigest(payload: Data, nonce: String, key: Data) -> String {
    var message = payload
    message.append(0)
    message.append(Data(nonce.utf8))
    let code = HMAC<SHA256>.authenticationCode(for: message, using: SymmetricKey(data: key))
    return hex(Data(code))
}

func parentName(pid: pid_t) -> String {
    NSRunningApplication(processIdentifier: pid)?.localizedName ?? "unknown"
}

func authorize() -> Never {
    let installation = validatedInstallation(stage: "authorize")
    let context = inputObject(stage: "authorize")
    let fields = context["fields"] as! [String]
    let repository = context["repository_root"] as! String
    let app = NSApplication.shared
    app.setActivationPolicy(.accessory)
    app.activate(ignoringOtherApps: true)
    let alert = NSAlert()
    alert.messageText = "Atom prose exception"
    alert.informativeText = "Validation field(s) \(fields) in \(repository) read prose.\n\nwaive — \(meanings["waive"]!)\n\ndecline — \(meanings["decline"]!)"
    alert.addButton(withTitle: "Waive")
    alert.addButton(withTitle: "Decline")
    alert.addButton(withTitle: "Cancel")
    let response = alert.runModal()
    if response == .alertThirdButtonReturn { fail("authorize", "operator cancelled without recording a decision") }
    let choice = response == .alertFirstButtonReturn ? "waive" : "decline"
    authenticate(choice: choice)
    let now = Date()
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let observedAt = formatter.string(from: now)
    let presentMarkers = harnessMarkers.filter { ProcessInfo.processInfo.environment[$0] != nil }
    let parentPID = getppid()
    let operatorRecord: [String: Any] = [
        "login_user": account,
        "uid": Int(getuid()),
        "approval_ui": "native-macos-window",
        "authentication_policy": "device-owner-authentication",
        "client_projection": installation.projection,
        "helper_path": installation.helperPath,
        "helper_sha256": installation.helperSHA256,
        "parent_process_name": parentName(pid: parentPID),
        "parent_process_pid": Int(parentPID),
        "observed_at": observedAt,
        "initiating_harness_markers": presentMarkers,
    ]
    let payload: [String: Any] = [
        "schema_version": contractVersion,
        "request_sha256": context["request_sha256"]!,
        "repository_root": repository,
        "fields": fields,
        "meanings": meanings,
        "choice": choice,
        "adopted_statement": meanings[choice]!,
        "date": String(observedAt.prefix(10)),
        "operator": operatorRecord,
    ]
    let payloadData = try! JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    let nonce = randomHex(byteCount: 32)
    let digest = authenticatedDigest(
        payload: payloadData,
        nonce: nonce,
        key: secret(createIfMissing: true, stage: "authorize")
    )
    let output: [String: Any] = [
        "schema_version": contractVersion,
        "status": "authorized",
        "helper_version": helperVersion,
        "service": service,
        "signed_payload_base64": payloadData.base64EncodedString(),
        "signed_payload_sha256": sha256(payloadData),
        "nonce": nonce,
        "digest": digest,
    ]
    let outputData = try! JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
    FileHandle.standardOutput.write(outputData)
    FileHandle.standardOutput.write(Data("\n".utf8))
    exit(0)
}

func verify() -> Never {
    _ = validatedInstallation(stage: "verify")
    guard CommandLine.arguments.count == 4 else {
        fail("verify", "usage: prose_waiver_approval verify <nonce> <digest>, with signed payload bytes on stdin")
    }
    let nonce = CommandLine.arguments[2]
    let suppliedDigest = CommandLine.arguments[3]
    guard nonce.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil,
          suppliedDigest.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil else {
        fail("verify", "nonce and digest must be lowercase SHA-256-shaped values")
    }
    let payload = FileHandle.standardInput.readDataToEndOfFile()
    guard !payload.isEmpty else { fail("verify", "signed payload is empty") }
    let key = secret(createIfMissing: false, stage: "verify")
    let observedDigest = authenticatedDigest(payload: payload, nonce: nonce, key: key)
    guard observedDigest == suppliedDigest else {
        fail("verify", "receipt proof does not match the protected approval key")
    }
    let output = try! JSONSerialization.data(
        withJSONObject: ["schema_version": contractVersion, "status": "verified"],
        options: [.sortedKeys]
    )
    FileHandle.standardOutput.write(output)
    FileHandle.standardOutput.write(Data("\n".utf8))
    exit(0)
}

guard CommandLine.arguments.count >= 2 else {
    fail("dispatch", "usage: prose_waiver_approval authorize|verify")
}
switch CommandLine.arguments[1] {
case "authorize":
    guard CommandLine.arguments.count == 2 else {
        fail("authorize", "the decision cannot be supplied by arguments; choose only in the native window")
    }
    authorize()
case "verify":
    verify()
default:
    fail("dispatch", "unknown action \(CommandLine.arguments[1]); use authorize or verify")
}
