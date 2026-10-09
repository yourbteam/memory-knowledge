using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

public static class StartupHook
{
    private const string HostingDiagnosticName = "Microsoft.Extensions.Hosting";
    private const string OperationNonceVariable = "ATLAS_RUNTIME_PROBE_OPERATION_NONCE";
    private const string CapturePathVariable = "ATLAS_RUNTIME_PROBE_OUTPUT";
    private const string TerminationPathVariable = "ATLAS_RUNTIME_PROBE_TERMINATION_OUTPUT";
    private const string ProfileVariable = "ATLAS_RUNTIME_PROBE_PROFILE";
    private const string EntryAssemblyNameVariable = "ATLAS_RUNTIME_PROBE_ENTRY_ASSEMBLY_NAME";
    private const string InterfaceTypeNameVariable = "ATLAS_RUNTIME_PROBE_INTERFACE_TYPE_NAME";
    private const string ExpectedRuntimeTypeVariable = "ATLAS_RUNTIME_PROBE_EXPECTED_RUNTIME_TYPE_NAME";
    private const string ProfileInputKeyVariable = "ATLAS_RUNTIME_PROBE_PROFILE_INPUT_KEY";
    private const string ProfileInputExpectedValueVariable = "ATLAS_RUNTIME_PROBE_PROFILE_INPUT_EXPECTED_VALUE";

    private static IDisposable? _subscription;
    private static int _hostBuiltHandled;
    private static ProbeInputs? _inputs;
    private static Exception? _issuedAbort;

    public static void Initialize()
    {
        _inputs = ReadAndValidateInputs();
        _issuedAbort = CreatePublicHostAbortedException();
        AppDomain.CurrentDomain.UnhandledException += OnUnhandledException;
        _subscription = DiagnosticListener.AllListeners.Subscribe(new ListenerObserver());
    }

    private static ProbeInputs ReadAndValidateInputs()
    {
        var nonceText = Environment.GetEnvironmentVariable(OperationNonceVariable);
        if (!Guid.TryParseExact(nonceText, "D", out var nonce))
        {
            throw new InvalidOperationException(
                "runtime_probe_invalid_operation_nonce: ATLAS_RUNTIME_PROBE_OPERATION_NONCE was missing or malformed; supply a per-run UUID in D format (8-4-4-4-12). The app entrypoint was not started.");
        }

        var capturePath = Environment.GetEnvironmentVariable(CapturePathVariable);
        var terminationPath = Environment.GetEnvironmentVariable(TerminationPathVariable);
        if (string.IsNullOrWhiteSpace(capturePath) || !Path.IsPathFullyQualified(capturePath)
            || string.IsNullOrWhiteSpace(terminationPath) || !Path.IsPathFullyQualified(terminationPath)
            || string.Equals(Path.GetFullPath(capturePath), Path.GetFullPath(terminationPath), StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "runtime_probe_output_paths_invalid: ATLAS_RUNTIME_PROBE_OUTPUT and ATLAS_RUNTIME_PROBE_TERMINATION_OUTPUT must both be absolute, distinct file paths; one is missing, relative, or collides with the other. The app entrypoint was not started.");
        }

        var profile = Environment.GetEnvironmentVariable(ProfileVariable);
        if (string.IsNullOrWhiteSpace(profile) || profile.Length > 64
            || profile.Any(character => !(char.IsAsciiLetterOrDigit(character) || character is '-' or '_' or '.')))
        {
            throw new InvalidOperationException(
                "runtime_probe_profile_invalid: ATLAS_RUNTIME_PROBE_PROFILE must be a nonempty 1-64 character label using ASCII letters, digits, dash, underscore, or period. The app entrypoint was not started.");
        }

        var entryAssemblyNameExpected = Environment.GetEnvironmentVariable(EntryAssemblyNameVariable);
        var interfaceTypeName = Environment.GetEnvironmentVariable(InterfaceTypeNameVariable);
        var expectedRuntimeTypeName = Environment.GetEnvironmentVariable(ExpectedRuntimeTypeVariable);
        var profileInputKey = Environment.GetEnvironmentVariable(ProfileInputKeyVariable);
        var profileInputExpectedValue = Environment.GetEnvironmentVariable(ProfileInputExpectedValueVariable);
        if (string.IsNullOrWhiteSpace(entryAssemblyNameExpected)
            || string.IsNullOrWhiteSpace(interfaceTypeName)
            || string.IsNullOrWhiteSpace(expectedRuntimeTypeName)
            || string.IsNullOrWhiteSpace(profileInputKey)
            || profileInputExpectedValue is null)
        {
            throw new InvalidOperationException(
                "runtime_probe_source_contract_missing: expected entry-assembly, interface, concrete-type, configuration-key, and configuration-value inputs were not all supplied. The app entrypoint was not started.");
        }

        var profileInputWasSet = Environment.GetEnvironmentVariables().Contains(profileInputKey);
        var profileInputActualValue = Environment.GetEnvironmentVariable(profileInputKey);
        if (!profileInputWasSet || !string.Equals(profileInputActualValue, profileInputExpectedValue, StringComparison.Ordinal))
        {
            var actualState = !profileInputWasSet ? "unset" : string.IsNullOrEmpty(profileInputActualValue) ? "empty" : "nonempty";
            var expectedState = string.IsNullOrEmpty(profileInputExpectedValue) ? "empty" : "nonempty";
            throw new InvalidOperationException(
                $"runtime_probe_profile_input_mismatch: configuration key '{profileInputKey}' arrived as '{actualState}'; the caller expected an explicit '{expectedState}' value for profile '{profile}'. The app entrypoint was not started.");
        }

        var entryAssembly = Assembly.GetEntryAssembly();
        var entryAssemblyName = entryAssembly?.GetName();
        if (entryAssembly is null || entryAssemblyName?.Name != entryAssemblyNameExpected || string.IsNullOrWhiteSpace(entryAssemblyName.FullName))
        {
            var actual = entryAssemblyName?.Name ?? "missing";
            throw new InvalidOperationException(
                $"runtime_probe_entry_assembly_mismatch: entry assembly name was '{actual}'; expected caller-validated assembly '{entryAssemblyNameExpected}'. The app entrypoint was not started.");
        }

        return new ProbeInputs(
            nonce.ToString("D"),
            profile,
            Environment.ProcessId,
            entryAssemblyName.FullName,
            entryAssembly.Location,
            Path.GetFullPath(capturePath),
            Path.GetFullPath(terminationPath),
            profileInputKey,
            profileInputExpectedValue,
            profileInputActualValue,
            interfaceTypeName,
            expectedRuntimeTypeName,
            entryAssembly);
    }

    private static Exception CreatePublicHostAbortedException()
    {
        var exceptionType = Type.GetType(
            "Microsoft.Extensions.Hosting.HostAbortedException, Microsoft.Extensions.Hosting.Abstractions",
            throwOnError: false);
        if (exceptionType is null || !exceptionType.IsPublic
            || !typeof(Exception).IsAssignableFrom(exceptionType)
            || exceptionType.Name != "HostAbortedException"
            || exceptionType.GetConstructor(Type.EmptyTypes) is null)
        {
            throw new InvalidOperationException(
                "runtime_probe_public_host_aborted_exception_unavailable: Microsoft.Extensions.Hosting.Abstractions did not expose a public HostAbortedException with a public parameterless constructor; the observer refuses to start the target entrypoint without the supported abort type.");
        }

        try
        {
            return Activator.CreateInstance(exceptionType) as Exception
                ?? throw new InvalidOperationException("runtime_probe_public_host_aborted_exception_unavailable");
        }
        catch (Exception)
        {
            throw new InvalidOperationException(
                "runtime_probe_public_host_aborted_exception_unavailable: the public HostAbortedException could not be constructed; the observer refuses to start the target entrypoint.");
        }
    }

    private static void OnUnhandledException(object sender, UnhandledExceptionEventArgs args)
    {
        var inputs = _inputs;
        var issuedAbort = _issuedAbort;
        if (inputs is null || issuedAbort is null
            || Volatile.Read(ref _hostBuiltHandled) == 0
            || !args.IsTerminating
            || !ReferenceEquals(args.ExceptionObject, issuedAbort))
        {
            return;
        }

        var record = new
        {
            schema_version = 1,
            operation_nonce = inputs.OperationNonce,
            profile = inputs.Profile,
            process_id = inputs.ProcessId,
            entry_assembly_identity = inputs.EntryAssemblyIdentity,
            entry_assembly_location = inputs.EntryAssemblyLocation,
            host_built_observed = true,
            intentional_host_abort = true,
            unhandled_exception_type = issuedAbort.GetType().FullName,
            process_terminating = true
        };
        WriteRecord(inputs.TerminationPath, record);
    }

    private sealed class ListenerObserver : IObserver<DiagnosticListener>
    {
        public void OnCompleted() { }
        public void OnError(Exception error) { }

        public void OnNext(DiagnosticListener listener)
        {
            if (listener.Name == HostingDiagnosticName)
            {
                listener.Subscribe(new HostEventObserver());
            }
        }
    }

    private sealed class HostEventObserver : IObserver<KeyValuePair<string, object?>>
    {
        public void OnCompleted() { }
        public void OnError(Exception error) { }

        public void OnNext(KeyValuePair<string, object?> value)
        {
            if (value.Key != "HostBuilt" || Interlocked.Exchange(ref _hostBuiltHandled, 1) != 0)
            {
                return;
            }

            var inputs = _inputs;
            if (inputs is null)
            {
                throw new InvalidOperationException("runtime_probe_inputs_unavailable_after_host_built");
            }

            var hostValue = value.Value;
            IHost? host = null;
            object? service = null;
            IServiceScope? scope = null;
            string? failureCode = null;
            string? failureMessage = null;
            var scopeDisposed = false;
            var hostDisposed = false;
            Type? serviceType = null;

            try
            {
                host = hostValue as IHost;
                if (host is null)
                {
                    failureCode = "host_built_value_not_i_host";
                    failureMessage = $"HostBuilt supplied '{hostValue?.GetType().FullName ?? "null"}'; expected Microsoft.Extensions.Hosting.IHost.";
                }
                else
                {
                    serviceType = inputs.EntryAssembly.GetType(inputs.InterfaceTypeName, throwOnError: false);
                    var expectedRuntimeType = inputs.EntryAssembly.GetType(inputs.ExpectedRuntimeTypeName, throwOnError: false);
                    if (serviceType is null || !serviceType.IsInterface || serviceType.Assembly != inputs.EntryAssembly)
                    {
                        failureCode = "interface_missing_from_entry_assembly";
                        failureMessage = $"The target entry assembly did not declare the caller-specified interface '{inputs.InterfaceTypeName}'; expected that exact interface in {inputs.EntryAssemblyIdentity}.";
                    }
                    else if (expectedRuntimeType is null || expectedRuntimeType.Assembly != inputs.EntryAssembly
                        || !expectedRuntimeType.IsClass || expectedRuntimeType.IsAbstract
                        || !serviceType.IsAssignableFrom(expectedRuntimeType))
                    {
                        failureCode = "expected_runtime_type_not_interface_candidate";
                        failureMessage = $"The caller-specified concrete type '{inputs.ExpectedRuntimeTypeName}' was not a concrete class implementing interface '{inputs.InterfaceTypeName}' in {inputs.EntryAssemblyIdentity}.";
                    }
                    else
                    {
                        try
                        {
                            scope = host.Services.GetRequiredService<IServiceScopeFactory>().CreateScope();
                            service = scope.ServiceProvider.GetService(serviceType);
                            if (service is null)
                            {
                                failureCode = "interface_service_not_registered";
                                failureMessage = $"The built host returned no scoped service for interface '{inputs.InterfaceTypeName}'; expected one registered instance.";
                            }
                        }
                        catch (Exception exception)
                        {
                            failureCode = "interface_service_resolution_failed";
                            failureMessage = $"Creating a scope or resolving interface '{inputs.InterfaceTypeName}' threw {exception.GetType().FullName}; expected one instance from the built host.";
                        }
                        finally
                        {
                            if (scope is not null)
                            {
                                try
                                {
                                    scope.Dispose();
                                    scopeDisposed = true;
                                }
                                catch (Exception)
                                {
                                    failureCode ??= "service_scope_disposal_failed";
                                    failureMessage ??= "Disposing the interface-service scope failed; expected scope disposal to complete before host disposal.";
                                }
                            }
                        }
                    }
                }
            }
            finally
            {
                if (host is not null)
                {
                    try
                    {
                        host.Dispose();
                        hostDisposed = true;
                    }
                    catch (Exception)
                    {
                        failureCode ??= "host_disposal_failed";
                        failureMessage ??= "Disposing the captured IHost failed; expected host disposal to complete before intentional abort.";
                    }
                }
            }

            var runtimeType = service?.GetType();
            if (failureCode is null && runtimeType?.FullName != inputs.ExpectedRuntimeTypeName)
            {
                failureCode = "selected_runtime_type_mismatch";
                failureMessage = $"The built host selected '{runtimeType?.FullName ?? "null"}'; profile '{inputs.Profile}' expected caller-validated type '{inputs.ExpectedRuntimeTypeName}'.";
            }
            var capture = new
            {
                schema_version = 1,
                operation_nonce = inputs.OperationNonce,
                profile = inputs.Profile,
                process_id = inputs.ProcessId,
                entry_assembly_identity = inputs.EntryAssemblyIdentity,
                entry_assembly_location = inputs.EntryAssemblyLocation,
                profile_input_key = inputs.ProfileInputKey,
                profile_input_state = string.IsNullOrEmpty(inputs.ProfileInputActualValue) ? "empty" : "nonempty",
                profile_input_matches = string.Equals(inputs.ProfileInputActualValue, inputs.ProfileInputExpectedValue, StringComparison.Ordinal),
                interface_full_name = serviceType?.FullName,
                interface_assembly_identity = serviceType?.Assembly.GetName().FullName,
                expected_runtime_type = inputs.ExpectedRuntimeTypeName,
                observed_runtime_type = runtimeType?.FullName,
                observed_runtime_assembly_identity = runtimeType?.Assembly.GetName().FullName,
                observed_runtime_assembly_location = runtimeType?.Assembly.Location,
                selection_matches = string.Equals(runtimeType?.FullName, inputs.ExpectedRuntimeTypeName, StringComparison.Ordinal),
                loaded_assemblies = AppDomain.CurrentDomain.GetAssemblies()
                    .Select(assembly => new
                    {
                        identity = assembly.GetName().FullName,
                        location = SafeAssemblyLocation(assembly)
                    })
                    .Where(assembly => !string.IsNullOrEmpty(assembly.location))
                    .OrderBy(assembly => assembly.identity, StringComparer.Ordinal)
                    .ThenBy(assembly => assembly.location, StringComparer.Ordinal)
                    .ToArray(),
                host_built_observed = true,
                host_type = host?.GetType().FullName ?? hostValue?.GetType().FullName,
                host_disposed = hostDisposed,
                scope_disposed = scopeDisposed,
                failure_code = failureCode,
                failure_message = failureMessage
            };
            WriteRecord(inputs.CapturePath, capture);

            var abort = _issuedAbort
                ?? throw new InvalidOperationException("runtime_probe_abort_exception_unavailable_after_host_built");
            throw abort;
        }
    }

    private static void WriteRecord<T>(string path, T record)
    {
        try
        {
            var bytes = JsonSerializer.SerializeToUtf8Bytes(record, new JsonSerializerOptions { WriteIndented = true });
            using var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            output.Write(bytes);
            output.Flush(flushToDisk: true);
        }
        catch (Exception)
        {
            // Missing evidence makes the external runner refuse the observation.
        }
    }

    private static string? SafeAssemblyLocation(Assembly assembly)
    {
        try
        {
            return assembly.IsDynamic ? null : assembly.Location;
        }
        catch (NotSupportedException)
        {
            return null;
        }
    }

    private sealed record ProbeInputs(
        string OperationNonce,
        string Profile,
        int ProcessId,
        string EntryAssemblyIdentity,
        string EntryAssemblyLocation,
        string CapturePath,
        string TerminationPath,
        string ProfileInputKey,
        string ProfileInputExpectedValue,
        string? ProfileInputActualValue,
        string InterfaceTypeName,
        string ExpectedRuntimeTypeName,
        Assembly EntryAssembly);
}
