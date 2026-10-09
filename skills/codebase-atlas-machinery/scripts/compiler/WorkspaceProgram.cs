using Microsoft.Build.Locator;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.MSBuild;
using Microsoft.CodeAnalysis.Text;
using System.Security.Cryptography;
using System.Text.Json;

if (args.Length != 5) throw new Exception("usage: extractor <project> <mirror-root> <repository-root> <target-framework> <lexical-manifest>");
var projectPath = Path.GetFullPath(args[0]);
var mirrorRoot = Path.GetFullPath(args[1]);
var repositoryRoot = Path.GetFullPath(args[2]);
var framework = args[3];
using var lexicalManifestDocument = JsonDocument.Parse(File.ReadAllBytes(args[4]));
var lexicalManifestRoot = lexicalManifestDocument.RootElement;
if (lexicalManifestRoot.ValueKind != JsonValueKind.Object || lexicalManifestRoot.GetProperty("schema_version").GetInt32() != 1)
 throw new Exception("lexical method manifest is malformed");
var admittedMethods = new HashSet<string>(StringComparer.Ordinal);
foreach (var item in lexicalManifestRoot.GetProperty("methods").EnumerateArray()) {
 var source = item.GetProperty("source"); var span = source.GetProperty("span");
 admittedMethods.Add(string.Join("|", item.GetProperty("method_name").GetString(), source.GetProperty("path").GetString(),
  source.GetProperty("sha256").GetString(), span.GetProperty("start_offset").GetInt32(), span.GetProperty("end_offset").GetInt32()));
}
var sdk = MSBuildLocator.RegisterDefaults();
var workspaceDiagnostics = new List<string>();
var props = new Dictionary<string,string>(StringComparer.Ordinal) {
 ["Configuration"]="Debug", ["TargetFramework"]=framework,
 ["BaseIntermediateOutputPath"]=Path.Combine(Path.GetDirectoryName(projectPath)!,"obj")+Path.DirectorySeparatorChar,
 ["MSBuildProjectExtensionsPath"]=Path.Combine(Path.GetDirectoryName(projectPath)!,"obj")+Path.DirectorySeparatorChar,
 ["ProjectAssetsFile"]=Path.Combine(Path.GetDirectoryName(projectPath)!,"obj","project.assets.json"),
 ["BaseOutputPath"]=Path.Combine(Path.GetDirectoryName(projectPath)!,"bin")+Path.DirectorySeparatorChar,
 ["OutputPath"]=Path.Combine(Path.GetDirectoryName(projectPath)!,"bin","Debug",framework)+Path.DirectorySeparatorChar,
 ["OutDir"]=Path.Combine(Path.GetDirectoryName(projectPath)!,"bin","Debug",framework)+Path.DirectorySeparatorChar,
 ["Restore"]="false", ["RestoreDuringBuild"]="false", ["BuildProjectReferences"]="false",
 ["SkipCompilerExecution"]="true", ["DesignTimeBuild"]="true", ["ProvideCommandLineArgs"]="true"
};
using var workspace = MSBuildWorkspace.Create(props);
workspace.RegisterWorkspaceFailedHandler(e => workspaceDiagnostics.Add(e.Diagnostic.Kind+":"+e.Diagnostic.Message));
var project = await workspace.OpenProjectAsync(projectPath);
var compilation = await project.GetCompilationAsync() ?? throw new Exception("workspace returned no compilation");
var diagnostics = compilation.GetDiagnostics();
var errors = diagnostics.Where(d=>d.Severity==DiagnosticSeverity.Error).Select(d=>d.ToString()).OrderBy(s=>s,StringComparer.Ordinal).ToArray();
if (errors.Length != 0) throw new Exception("compiler errors: "+string.Join(" | ",errors));
if (workspaceDiagnostics.Any(s=>s.StartsWith("Failure:",StringComparison.Ordinal))) throw new Exception("workspace failures: "+string.Join(" | ",workspaceDiagnostics));

static IEnumerable<INamedTypeSymbol> Types(INamespaceSymbol ns) {
 foreach (var type in ns.GetTypeMembers()) { yield return type; foreach(var nested in Nested(type)) yield return nested; }
 foreach (var child in ns.GetNamespaceMembers()) foreach(var type in Types(child)) yield return type;
}
static IEnumerable<INamedTypeSymbol> Nested(INamedTypeSymbol type) { foreach(var child in type.GetTypeMembers()) { yield return child; foreach(var n in Nested(child)) yield return n; } }
static int CodePointOffset(SourceText text,int utf16) => text.ToString(new TextSpan(0,utf16)).EnumerateRunes().Count();
static string CanonicalPath(string mirror,string repo,string path) {
 var relative=Path.GetRelativePath(mirror,path);
 if (relative==".." || relative.StartsWith(".."+Path.DirectorySeparatorChar,StringComparison.Ordinal) || Path.IsPathRooted(relative)) throw new Exception("source anchor escapes protected mirror: "+path);
 return Path.Combine(repo,relative).Replace(Path.DirectorySeparatorChar,'/');
}
object Anchor(string path, TextSpan span) {
 var absolute=Path.GetFullPath(path); var tree=compilation.SyntaxTrees.SingleOrDefault(t=>Path.GetFullPath(t.FilePath)==absolute) ?? throw new Exception("anchor syntax tree is absent");
 var text=tree.GetText(); var lines=text.Lines; var start=lines.GetLinePosition(span.Start); var end=lines.GetLinePosition(span.End); var canonical=CanonicalPath(mirrorRoot,repositoryRoot,absolute);
 return new SortedDictionary<string,object?>(StringComparer.Ordinal) {
  ["path"]=Path.GetRelativePath(repositoryRoot,canonical).Replace(Path.DirectorySeparatorChar,'/'),
  ["sha256"]=Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(absolute))),
  ["span"]=new SortedDictionary<string,object?>(StringComparer.Ordinal) { ["start_line"]=start.Line+1,["start_column"]=start.Character+1,["end_line"]=end.Line+1,["end_column"]=end.Character+1,["start_offset"]=CodePointOffset(text,span.Start),["end_offset"]=CodePointOffset(text,span.End),["offset_unit"]="unicode_codepoint" }
 };
}
string? ConstantString(AttributeSyntax attribute, SemanticModel model) { var expr=attribute.ArgumentList?.Arguments.FirstOrDefault()?.Expression; var value=expr is null?default:model.GetConstantValue(expr); return value.HasValue?value.Value as string:null; }
var records=new List<SortedDictionary<string,object?>>();
var unresolved=new List<SortedDictionary<string,object?>>();
var sourceCallEdges=new List<SortedDictionary<string,object?>>();
var sourceCallUnresolved=new List<SortedDictionary<string,object?>>();
var routeRoots=new List<(string Route,string Verb,INamedTypeSymbol Concrete,IMethodSymbol Method)>();
var allTypes=Types(compilation.Assembly.GlobalNamespace).ToArray();
foreach(var tree in compilation.SyntaxTrees.OrderBy(t=>t.FilePath,StringComparer.Ordinal)) {
 var root=await tree.GetRootAsync(); var model=compilation.GetSemanticModel(tree);
 foreach(var methodNode in root.DescendantNodes().OfType<MethodDeclarationSyntax>()) {
  if (model.GetDeclaredSymbol(methodNode) is not IMethodSymbol action || action.MethodKind!=MethodKind.Ordinary) continue;
  var routeAttrs=methodNode.AttributeLists.SelectMany(x=>x.Attributes).Where(a=>a.Name.ToString().EndsWith("HttpGet",StringComparison.Ordinal)||a.Name.ToString().EndsWith("HttpPost",StringComparison.Ordinal)||a.Name.ToString().EndsWith("HttpPut",StringComparison.Ordinal)||a.Name.ToString().EndsWith("HttpDelete",StringComparison.Ordinal)||a.Name.ToString().EndsWith("HttpPatch",StringComparison.Ordinal)).ToArray();
  if(routeAttrs.Length==0) continue;
  foreach(var invocation in methodNode.DescendantNodes().OfType<InvocationExpressionSyntax>()) {
   if(invocation.Expression is not MemberAccessExpressionSyntax member) continue;
   var targetInfo=model.GetSymbolInfo(invocation);
   var receiverInfo=model.GetSymbolInfo(member.Expression);
   var target=targetInfo.Symbol as IMethodSymbol;
   var receiver=receiverInfo.Symbol as IParameterSymbol;
   if((target is null && targetInfo.CandidateReason==CandidateReason.Ambiguous) || (receiver is null && receiverInfo.CandidateSymbols.Length>1))
    throw new Exception("ambiguous compiler call or receiver binding at "+tree.FilePath+":"+invocation.SpanStart);
   if(target is null || receiver?.Type is not INamedTypeSymbol service || service.TypeKind==TypeKind.Error) {
    if(targetInfo.CandidateSymbols.OfType<IMethodSymbol>().Any() || receiverInfo.CandidateSymbols.Length>0)
     unresolved.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){["kind"]="route_invocation_binding_unresolved",["action_method"]=action.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["source"]=Anchor(tree.FilePath,invocation.Span),["reason"]="compiler did not produce one bound call and parameter receiver"});
    continue;
   }
   if(!SymbolEqualityComparer.Default.Equals(target.ContainingType,service) || service.TypeKind!=TypeKind.Interface || !service.IsGenericType || service.TypeArguments.Length==0) {
    unresolved.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){["kind"]="unsupported_route_invocation_shape",["action_method"]=action.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["source"]=Anchor(tree.FilePath,invocation.Span),["reason"]="bound call is not a closed-generic interface member on a parameter receiver"});
    continue;
   }
   var receiverSyntax=receiver.DeclaringSyntaxReferences.SingleOrDefault()?.GetSyntax();
   if(receiverSyntax is not ParameterSyntax parameterSyntax || parameterSyntax.Parent?.Parent is not TypeDeclarationSyntax primaryOwner
      || primaryOwner.ParameterList is null || !primaryOwner.ParameterList.Parameters.Contains(parameterSyntax)) {
    unresolved.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){["kind"]="unsupported_injection_shape",["action_method"]=action.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["source"]=Anchor(tree.FilePath,invocation.Span),["reason"]="receiver parameter is not declared by a primary constructor"});
    continue;
   }
   var owner=methodNode.Parent?.AncestorsAndSelf().OfType<ClassDeclarationSyntax>().FirstOrDefault();
   if(owner is null) continue;
   var classRouteAttrs=owner.AttributeLists.SelectMany(x=>x.Attributes)
    .Where(a=>model.GetSymbolInfo(a).Symbol is IMethodSymbol ctor && ctor.ContainingType.Name=="RouteAttribute").ToArray();
   string? prefix=null;
   if(classRouteAttrs.Length==1) prefix=ConstantString(classRouteAttrs[0],model);
   if(classRouteAttrs.Length>1) {
    unresolved.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){["kind"]="controller_route_ambiguous",["action_method"]=action.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["source"]=Anchor(tree.FilePath,methodNode.Span),["reason"]="controller has multiple Route attributes; lexical route composition is ambiguous"});
    continue;
   }
   var routeShapes=new List<(string Verb,string Route)>();
   foreach(var routeAttr in routeAttrs) {
    var ctor=model.GetSymbolInfo(routeAttr).Symbol as IMethodSymbol;
    var attrName=ctor?.ContainingType.Name ?? routeAttr.Name.ToString().Split('.').Last();
    var verb=attrName.StartsWith("Http",StringComparison.Ordinal)?attrName[4..].Replace("Attribute","").ToUpperInvariant():"";
    string? actionRoute;
    var routeArguments=routeAttr.ArgumentList?.Arguments ?? default;
    if(routeArguments.Count==0) actionRoute="";
    else if(routeArguments.Count==1) actionRoute=ConstantString(routeAttr,model);
    else actionRoute=null;
    if(string.IsNullOrWhiteSpace(verb) || actionRoute is null) {
     unresolved.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){["kind"]="route_action_unresolved",["action_method"]=action.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["source"]=Anchor(tree.FilePath,routeAttr.Span),["reason"]="HTTP attribute does not provide one constant route literal"});
     continue;
    }
    var absolute=actionRoute.StartsWith("/",StringComparison.Ordinal)||actionRoute.StartsWith("~/",StringComparison.Ordinal);
    var normalizedAction=actionRoute.StartsWith("~/",StringComparison.Ordinal)?actionRoute[2..]:actionRoute.TrimStart('/');
    var route=string.Join("/",((absolute?null:prefix) is string p?new[]{p,normalizedAction}:new[]{normalizedAction})
      .Where(p=>!string.IsNullOrEmpty(p)).Select(p=>p.Trim('/')));
    routeShapes.Add((verb,route));
   }
   var implementations=allTypes.Where(t=>t.AllInterfaces.Any(i=>SymbolEqualityComparer.Default.Equals(i,service))).ToArray();
   var boundImpls=new List<(INamedTypeSymbol Concrete, IMethodSymbol Method)>();
   foreach(var implType in implementations) if(implType.FindImplementationForInterfaceMember(target) is IMethodSymbol impl) boundImpls.Add((implType,impl));
   if(boundImpls.Count==0) unresolved.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){["kind"]="implementation_correspondence_unresolved",["action_method"]=action.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["source"]=Anchor(tree.FilePath,member.Name.Span),["reason"]="no source implementation correspondence was found in the project compilation"});
   foreach(var routeShape in routeShapes) foreach(var implPair in boundImpls) {
    var impl=implPair.Method;
    var registrationSyntax=new List<object>();
    foreach(var regTree in compilation.SyntaxTrees) {
     var rr=await regTree.GetRootAsync(); var rm=compilation.GetSemanticModel(regTree);
     foreach(var node in rr.DescendantNodes().OfType<InvocationExpressionSyntax>()) {
      if(node.Expression is not MemberAccessExpressionSyntax regMember || regMember.Name is not GenericNameSyntax generic || generic.Identifier.ValueText!="AddScoped" || generic.TypeArgumentList.Arguments.Count!=2) continue;
      if(rm.GetSymbolInfo(node).Symbol is not IMethodSymbol reg || reg.TypeArguments.Length!=2) continue;
      if(SymbolEqualityComparer.Default.Equals(reg.TypeArguments[0],service) && SymbolEqualityComparer.Default.Equals(reg.TypeArguments[1],implPair.Concrete))
       registrationSyntax.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){["service_type"]=reg.TypeArguments[0].ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["implementation_type"]=reg.TypeArguments[1].ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["syntax"]=node.ToString(),["source"]=Anchor(regTree.FilePath,node.Span),["runtime_DI_selection_proven"]=false});
     }
    }
    var targetLocation=target.Locations.FirstOrDefault(l=>l.IsInSource) ?? throw new Exception("bound interface member has no source location");
    var implLocation=impl.Locations.FirstOrDefault(l=>l.IsInSource) ?? throw new Exception("implementation member has no source location");
    records.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){
     ["route"]=routeShape.Route,["http_method"]=routeShape.Verb,["action_method"]=action.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["action_source"]=Anchor(tree.FilePath,methodNode.Span),["call_site_source"]=Anchor(tree.FilePath,member.Name.Span),
     ["service_parameter"]=receiver.Name,["service_type"]=service.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["service_parameter_source"]=Anchor(tree.FilePath,receiver.DeclaringSyntaxReferences.Single().GetSyntax().Span),
     ["bound_member"]=target.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["bound_member_source"]=Anchor(targetLocation.SourceTree!.FilePath,targetLocation.SourceSpan),["implementation_method"]=impl.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["implementation_method_containing_type"]=impl.ContainingType.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["implementation_type"]=implPair.Concrete.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["implementation_source"]=Anchor(implLocation.SourceTree!.FilePath,implLocation.SourceSpan),["compiler_implementation_match"]=true,["registrations"]=registrationSyntax,["runtime_DI_selection_proven"]=false
    });
    routeRoots.Add((routeShape.Route,routeShape.Verb,implPair.Concrete,impl));
   }
  }
 }
}
const int MaxSourceCallRoots=20000, MaxSourceCallNodes=50000, MaxSourceCallEdges=250000;
const int MaxInspectedSourceInvocations=500000, MaxSourceCallUnsupported=250000;
const int MaxNestedBodyExclusions=100000, MaxSourceCallGraphBytes=134217728, MaxImpactWitnessHops=2000000;
const long MaxSourceCallTraversalWork=2000000, MaxSourceCallCompatibilityRecords=2000000;
var roots=new List<SortedDictionary<string,object?>>();
var nodes=new List<SortedDictionary<string,object?>>();
var graphEdges=new List<SortedDictionary<string,object?>>();
var graphUnsupported=new List<SortedDictionary<string,object?>>();
var nestedExclusions=new List<SortedDictionary<string,object?>>();
var methodByNode=new Dictionary<string,(IMethodSymbol Method,MethodDeclarationSyntax? Syntax)>();
var nodeQueue=new Queue<string>();
string NodeId(IMethodSymbol candidate, MethodDeclarationSyntax? declaration=null) {
 var method=candidate.OriginalDefinition;
 var syntax=declaration ?? (method.DeclaringSyntaxReferences.SingleOrDefault()?.GetSyntax() as MethodDeclarationSyntax);
 if(syntax is null) throw new Exception("source-call graph method has no unique method declaration: "+method.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat));
 var anchor=(SortedDictionary<string,object?>)Anchor(syntax.SyntaxTree.FilePath,syntax.Span);
 var span=(SortedDictionary<string,object?>)anchor["span"]!;
 return "method:"+anchor["path"]+":"+span["start_offset"]+":"+span["end_offset"];
}
string AddNode(IMethodSymbol candidate, MethodDeclarationSyntax? declaration=null) {
 var method=candidate.OriginalDefinition;
 var syntax=declaration ?? (method.DeclaringSyntaxReferences.SingleOrDefault()?.GetSyntax() as MethodDeclarationSyntax);
 var id=NodeId(method,syntax);
 if(methodByNode.ContainsKey(id)) return id;
 if(methodByNode.Count>=MaxSourceCallNodes) throw new Exception("source-call graph node cap exceeded; no partial graph emitted");
 methodByNode.Add(id,(method,syntax)); nodeQueue.Enqueue(id);
 nodes.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){
  ["id"]=id,["method"]=method.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
  ["containing_type"]=method.ContainingType.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
  ["source"]=Anchor(syntax!.SyntaxTree.FilePath,syntax.Span)
 });
 return id;
}
foreach(var root in routeRoots.OrderBy(x=>x.Route,StringComparer.Ordinal).ThenBy(x=>x.Verb,StringComparer.Ordinal)
 .ThenBy(x=>x.Concrete.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),StringComparer.Ordinal)
 .ThenBy(x=>x.Method.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),StringComparer.Ordinal)) {
 if(roots.Count>=MaxSourceCallRoots) throw new Exception("source-call graph root cap exceeded; no partial graph emitted");
 var method=root.Method.OriginalDefinition;
 var syntax=method.DeclaringSyntaxReferences.SingleOrDefault()?.GetSyntax() as MethodDeclarationSyntax;
 if(syntax is null) throw new Exception("mapped handler implementation has no unique source method declaration");
  var rootAnchor=(SortedDictionary<string,object?>)Anchor(syntax.SyntaxTree.FilePath,syntax.Span);
  var rootSpan=(SortedDictionary<string,object?>)rootAnchor["span"]!;
  var rootAdmission=string.Join("|",method.Name,(string)rootAnchor["path"]!, (string)rootAnchor["sha256"]!,
   (int)rootSpan["start_offset"]!, (int)rootSpan["end_offset"]!);
  if(!admittedMethods.Contains(rootAdmission)) throw new Exception("mapped handler root is not an exact admitted lexical method");
  var nodeId=AddNode(method,syntax);
 roots.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){
  ["route"]=root.Route,["http_method"]=root.Verb,
  ["implementation_type"]=root.Concrete.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
  ["implementation_method"]=root.Method.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
  ["root_method"]=method.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
  ["root_node_id"]=nodeId,["root_source"]=Anchor(syntax.SyntaxTree.FilePath,syntax.Span)
 });
}
var edgeKeys=new HashSet<string>(StringComparer.Ordinal);
var unsupportedKeys=new HashSet<string>(StringComparer.Ordinal);
var exclusionKeys=new HashSet<string>(StringComparer.Ordinal);
int inspectedInvocations=0; long traversalWork=0, compatibilityRecords=0;
while(nodeQueue.Count>0) {
 var callerId=nodeQueue.Dequeue();
 var (caller,callerNode)=methodByNode[callerId];
 var callerAnchor=callerNode is null ? Anchor(caller.Locations.First(l=>l.IsInSource).SourceTree!.FilePath,caller.Locations.First(l=>l.IsInSource).SourceSpan)
  : Anchor(callerNode.SyntaxTree.FilePath,callerNode.Span);
 if(callerNode is null || (callerNode.Body is null && callerNode.ExpressionBody is null)) {
  graphUnsupported.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){
   ["caller_node_id"]=callerId,["caller_method"]=caller.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
   ["caller_source"]=callerAnchor,["call_site_source"]=callerAnchor,
   ["kind"]="unsupported_source_method_body",["reason"]="visited source method has no block or expression body"
  });
  if(graphUnsupported.Count>MaxSourceCallUnsupported) throw new Exception("source-call unsupported-call cap exceeded; no partial graph emitted");
  continue;
 }
 var callerTree=callerNode.SyntaxTree;
 var model=compilation.GetSemanticModel(callerTree);
 IEnumerable<SyntaxNode> bodyRoots=callerNode.Body is not null ? new[]{(SyntaxNode)callerNode.Body}
  : new[]{callerNode.ExpressionBody!.Expression};
 IEnumerable<SyntaxNode> BodyDescendants(SyntaxNode body) => callerNode.Body is not null
  ? body.DescendantNodes(descendIntoChildren: node=>node is not AnonymousFunctionExpressionSyntax && node is not LocalFunctionStatementSyntax)
  : body.DescendantNodesAndSelf(descendIntoChildren: node=>node is not AnonymousFunctionExpressionSyntax && node is not LocalFunctionStatementSyntax);
 var excludedBodies=bodyRoots.SelectMany(BodyDescendants)
  .Where(node=>node is AnonymousFunctionExpressionSyntax || node is LocalFunctionStatementSyntax);
 foreach(var nested in excludedBodies) {
  var kind=nested is LocalFunctionStatementSyntax ? "local_function" : "anonymous_function";
  var anchor=Anchor(callerTree.FilePath,nested.Span);
  var span=(SortedDictionary<string,object?>)((SortedDictionary<string,object?>)anchor)["span"]!;
  var key=callerId+"|"+callerTree.FilePath+":"+span["start_offset"]+":"+span["end_offset"]+"|"+kind;
  if(!exclusionKeys.Add(key)) continue;
  nestedExclusions.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){
   ["caller_node_id"]=callerId,["caller_method"]=caller.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
   ["caller_source"]=callerAnchor,["nested_body_kind"]=kind,["source"]=anchor,
   ["reason"]="nested local-function or anonymous-function body is excluded from direct source-call traversal"
  });
  if(nestedExclusions.Count>MaxNestedBodyExclusions) throw new Exception("source-call nested-body exclusion cap exceeded; no partial graph emitted");
 }
 var callNodes=bodyRoots.SelectMany(BodyDescendants).OfType<InvocationExpressionSyntax>();
 foreach(var invocation in callNodes) {
  traversalWork++;
  if(traversalWork>MaxSourceCallTraversalWork) throw new Exception("source-call graph traversal-work cap exceeded; no partial graph emitted");
  inspectedInvocations++;
  if(inspectedInvocations>MaxInspectedSourceInvocations) throw new Exception("source-call inspected-invocation cap exceeded; no partial graph emitted");
  var sourceInfo=model.GetSymbolInfo(invocation);
  var called=sourceInfo.Symbol as IMethodSymbol;
  var calledNode=called is {DeclaringSyntaxReferences.Length:1}
   ? called.DeclaringSyntaxReferences[0].GetSyntax() as MethodDeclarationSyntax : null;
  var supportedSourceMethod=called is not null && called.MethodKind==MethodKind.Ordinary &&
   !called.IsExtensionMethod && called.ReducedFrom is null && called.ContainingAssembly==compilation.Assembly &&
   called.DeclaringSyntaxReferences.Length==1 && calledNode is not null &&
   (calledNode.Body is not null || calledNode.ExpressionBody is not null);
  var supportedStaticSourceShape=supportedSourceMethod && called!.IsStatic && called.Arity==0;
  var supportedInstanceSourceShape=supportedSourceMethod && !called!.IsStatic && called.Arity==0 &&
   !called.IsVirtual && !called.IsAbstract && !called.IsOverride;
  var unsupportedGenericSourceShape=supportedSourceMethod && called!.IsStatic && called.Arity>0;
  var dispatchKind=supportedStaticSourceShape ? "static_source"
   : supportedInstanceSourceShape ? "non_virtual_instance_source" : null;
  var callAnchor=Anchor(callerTree.FilePath,invocation.Span);
  var callSpan=(SortedDictionary<string,object?>)((SortedDictionary<string,object?>)callAnchor)["span"]!;
  if(dispatchKind is null) {
   if(sourceInfo.CandidateReason==CandidateReason.Ambiguous)
    throw new Exception("ambiguous compiler source call at "+callerTree.FilePath+":"+invocation.SpanStart);
   var reason=sourceInfo.Symbol is null ? "call is not one bound ordinary same-compilation source method"
    : unsupportedGenericSourceShape ? "generic source method is outside the supported lexical source-call shape"
    : "bound call is outside the supported same-compilation static or non-virtual instance source-method shape";
   var key=callerId+"|"+callerTree.FilePath+":"+callSpan["start_offset"]+":"+callSpan["end_offset"];
   if(unsupportedKeys.Add(key)) graphUnsupported.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){
    ["caller_node_id"]=callerId,["caller_method"]=caller.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
    ["caller_source"]=callerAnchor,["call_site_source"]=callAnchor,
    ["kind"]="unsupported_source_call",["reason"]=reason
   });
   if(graphUnsupported.Count>MaxSourceCallUnsupported) throw new Exception("source-call unsupported-call cap exceeded; no partial graph emitted");
   continue;
  }
  var candidateAnchor=(SortedDictionary<string,object?>)Anchor(calledNode!.SyntaxTree.FilePath,calledNode.Span);
  var candidateSpan=(SortedDictionary<string,object?>)candidateAnchor["span"]!;
  var admissionKey=string.Join("|",called!.Name,(string)candidateAnchor["path"]!, (string)candidateAnchor["sha256"]!,
   (int)candidateSpan["start_offset"]!, (int)candidateSpan["end_offset"]!);
  if(!admittedMethods.Contains(admissionKey)) {
   var key=callerId+"|"+callerTree.FilePath+":"+callSpan["start_offset"]+":"+callSpan["end_offset"]+"|unsupported_lexical_source_method";
   if(unsupportedKeys.Add(key)) graphUnsupported.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){
    ["caller_node_id"]=callerId,["caller_method"]=caller.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
    ["caller_source"]=callerAnchor,["call_site_source"]=callAnchor,
    ["kind"]="unsupported_lexical_source_method",["reason"]="complete compiler method declaration does not exactly match one saved lexical method fact",
    ["callee_method"]=called.ContainingType.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat)+"."+called.Name+"("+
     string.Join(", ",called.Parameters.Select(parameter=>parameter.Type.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat)))+")",
    ["callee_source"]=candidateAnchor
   });
   if(graphUnsupported.Count>MaxSourceCallUnsupported) throw new Exception("source-call unsupported-call cap exceeded; no partial graph emitted");
   continue;
  }
  var callee=called!.OriginalDefinition;
  var calleeId=AddNode(callee,calledNode);
  var edgeKey=callerId+"|"+callerTree.FilePath+":"+callSpan["start_offset"]+":"+callSpan["end_offset"];
  if(!edgeKeys.Add(edgeKey)) throw new Exception("duplicate source-call graph callsite; no partial graph emitted");
  if(graphEdges.Count>=MaxSourceCallEdges) throw new Exception("source-call graph edge cap exceeded; no partial graph emitted");
  graphEdges.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){
   ["caller_node_id"]=callerId,["callee_node_id"]=calleeId,
   ["caller_method"]=caller.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),["caller_source"]=callerAnchor,
   ["callee_method"]=callee.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
   ["callee_containing_type"]=callee.ContainingType.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat),
   ["callee_source"]=Anchor(calledNode!.SyntaxTree.FilePath,calledNode.Span),["call_site_source"]=callAnchor,
   ["dispatch_kind"]=dispatchKind,["compiler_binding_confirmed"]=true,
   ["runtime_reachability_proven"]=false,["runtime_DI_selection_proven"]=false
  });
 }
}
if(roots.Count!=routeRoots.Count) throw new Exception("source-call graph omitted a mapped route root");
var graphEdgesByCaller=graphEdges.GroupBy(edge=>(string)edge["caller_node_id"]!,StringComparer.Ordinal)
 .ToDictionary(group=>group.Key,group=>group.ToArray(),StringComparer.Ordinal);
var unsupportedByCaller=graphUnsupported.GroupBy(item=>(string)item["caller_node_id"]!,StringComparer.Ordinal)
 .ToDictionary(group=>group.Key,group=>group.ToArray(),StringComparer.Ordinal);
foreach(var root in roots) {
 var route=(string)root["route"]!; var verb=(string)root["http_method"]!;
 var implementationType=(string)root["implementation_type"]!; var implementationMethod=(string)root["implementation_method"]!;
 var rootNodeId=(string)root["root_node_id"]!;
 foreach(var edge in graphEdgesByCaller.GetValueOrDefault(rootNodeId) ?? Array.Empty<SortedDictionary<string,object?>>()) {
  compatibilityRecords++;
  if(compatibilityRecords>MaxSourceCallCompatibilityRecords) throw new Exception("source-call compatibility projection cap exceeded; no partial graph emitted");
  sourceCallEdges.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){
   ["route"]=route,["http_method"]=verb,["implementation_type"]=implementationType,
   ["implementation_method"]=implementationMethod,["caller_method"]=root["root_method"],
   ["caller_source"]=root["root_source"],["callee_method"]=edge["callee_method"],
   ["callee_containing_type"]=edge["callee_containing_type"],["callee_source"]=edge["callee_source"],
   ["call_site_source"]=edge["call_site_source"],["dispatch_kind"]=edge["dispatch_kind"],
   ["compiler_binding_confirmed"]=true,["runtime_reachability_proven"]=false,["runtime_DI_selection_proven"]=false
  });
 }
 foreach(var limitation in unsupportedByCaller.GetValueOrDefault(rootNodeId) ?? Array.Empty<SortedDictionary<string,object?>>()) {
  compatibilityRecords++;
  if(compatibilityRecords>MaxSourceCallCompatibilityRecords) throw new Exception("source-call compatibility projection cap exceeded; no partial graph emitted");
  sourceCallUnresolved.Add(new SortedDictionary<string,object?>(StringComparer.Ordinal){
   ["route"]=route,["http_method"]=verb,["implementation_type"]=implementationType,
   ["implementation_method"]=implementationMethod,["caller_method"]=limitation["caller_method"],
   ["caller_source"]=limitation["caller_source"],["kind"]=(string)limitation["kind"]! == "unsupported_source_call" ? "unsupported_handler_source_call" : limitation["kind"],
   ["source"]=limitation["call_site_source"],["reason"]=limitation["reason"]
  });
 }
}
string EdgeSortKey(SortedDictionary<string,object?> edge) {
 var anchor=(SortedDictionary<string,object?>)edge["call_site_source"]!;
 var span=(SortedDictionary<string,object?>)anchor["span"]!;
 return anchor["path"]+"\0"+Convert.ToInt64(span["start_offset"]).ToString("D12",System.Globalization.CultureInfo.InvariantCulture);
}
var orderedGraphEdges=graphEdges.OrderBy(EdgeSortKey,StringComparer.Ordinal)
 .ThenBy(edge=>edge["caller_node_id"]!.ToString(),StringComparer.Ordinal).ToArray();
var sourceCallGraph=new SortedDictionary<string,object?>(StringComparer.Ordinal){
 ["schema_version"]=1,["status"]="complete",
 ["caps"]=new SortedDictionary<string,object?>(StringComparer.Ordinal){
  ["roots"]=MaxSourceCallRoots,["nodes"]=MaxSourceCallNodes,["edges"]=MaxSourceCallEdges,
  ["inspected_invocations"]=MaxInspectedSourceInvocations,["unsupported"]=MaxSourceCallUnsupported,
  ["nested_body_exclusions"]=MaxNestedBodyExclusions,["serialized_graph_bytes"]=MaxSourceCallGraphBytes,
  ["impact_witness_hops"]=MaxImpactWitnessHops,["traversal_work"]=MaxSourceCallTraversalWork,
  ["compatibility_records"]=MaxSourceCallCompatibilityRecords
 },
 ["counts"]=new SortedDictionary<string,object?>(StringComparer.Ordinal){
  ["roots"]=roots.Count,["nodes"]=nodes.Count,["edges"]=graphEdges.Count,
  ["inspected_invocations"]=inspectedInvocations,["unsupported"]=graphUnsupported.Count,
  ["nested_body_exclusions"]=nestedExclusions.Count,["method_bodies_traversed"]=nodes.Count,
  ["traversal_work"]=traversalWork,["compatibility_records"]=compatibilityRecords,["serialized_graph_bytes"]=0
 },
 ["roots"]=roots.OrderBy(root=>root["route"]!.ToString(),StringComparer.Ordinal)
  .ThenBy(root=>root["http_method"]!.ToString(),StringComparer.Ordinal)
  .ThenBy(root=>root["implementation_type"]!.ToString(),StringComparer.Ordinal)
  .ThenBy(root=>root["implementation_method"]!.ToString(),StringComparer.Ordinal).ToArray(),
 ["nodes"]=nodes.OrderBy(node=>node["id"]!.ToString(),StringComparer.Ordinal).ToArray(),
 ["edges"]=orderedGraphEdges,
 ["unsupported"]=graphUnsupported.OrderBy(item=>EdgeSortKey(new SortedDictionary<string,object?>(StringComparer.Ordinal){["call_site_source"]=item["call_site_source"]}),StringComparer.Ordinal)
  .ThenBy(item=>item["caller_node_id"]!.ToString(),StringComparer.Ordinal).ToArray(),
 ["nested_body_exclusions"]=nestedExclusions.OrderBy(item=>{var anchor=(SortedDictionary<string,object?>)item["source"]!;var span=(SortedDictionary<string,object?>)anchor["span"]!;return anchor["path"]+"\0"+Convert.ToInt64(span["start_offset"]).ToString("D12",System.Globalization.CultureInfo.InvariantCulture);},StringComparer.Ordinal)
  .ThenBy(item=>item["caller_node_id"]!.ToString(),StringComparer.Ordinal).ToArray()
};
byte[] graphBytes=Array.Empty<byte>();
for(int attempt=0;attempt<4;attempt++) {
 graphBytes=JsonSerializer.SerializeToUtf8Bytes(sourceCallGraph);
 var counts=(SortedDictionary<string,object?>)sourceCallGraph["counts"]!;
 if(Convert.ToInt32(counts["serialized_graph_bytes"])==graphBytes.Length) break;
 counts["serialized_graph_bytes"]=graphBytes.Length;
 if(attempt==3) throw new Exception("source-call graph byte count did not stabilize; no partial graph emitted");
}
if(graphBytes.Length>MaxSourceCallGraphBytes) throw new Exception("source-call graph serialized-output cap exceeded; no partial graph emitted");
var buildAssembly=System.Reflection.Assembly.Load("Microsoft.Build");
var projectCollectionType=buildAssembly.GetType("Microsoft.Build.Evaluation.ProjectCollection") ?? throw new Exception("Microsoft.Build ProjectCollection is unavailable");
var projectCollection=Activator.CreateInstance(projectCollectionType,new object?[]{props}) ?? throw new Exception("could not create MSBuild ProjectCollection");
var evaluatedProject=projectCollectionType.GetMethod("LoadProject",new[]{typeof(string)})?.Invoke(projectCollection,new object[]{projectPath}) ?? throw new Exception("could not evaluate mirrored project");
var importCollection=evaluatedProject.GetType().GetProperty("Imports")?.GetValue(evaluatedProject) as System.Collections.IEnumerable ?? throw new Exception("MSBuild import list is unavailable");
var importPaths=importCollection.Cast<object>().Select(item=>{
 var imported=item.GetType().GetProperty("ImportedProject")?.GetValue(item);
 return imported?.GetType().GetProperty("FullPath")?.GetValue(imported) as string;
}).Where(path=>path is not null).Cast<string>().Append(projectPath);
var imports=importPaths.Distinct(StringComparer.Ordinal).OrderBy(p=>p,StringComparer.Ordinal).Select(path=>{
 var full=Path.GetFullPath(path); var rel=Path.GetRelativePath(mirrorRoot,full);
 var inMirror=rel!=".."&&!rel.StartsWith(".."+Path.DirectorySeparatorChar,StringComparison.Ordinal)&&!Path.IsPathRooted(rel);
 var logical=inMirror?"repo/"+rel.Replace(Path.DirectorySeparatorChar,'/') : "external/"+full.Replace(Path.DirectorySeparatorChar,'/').TrimStart('/');
 if(!File.Exists(full)) throw new Exception("evaluated MSBuild import is missing: "+full);
 return new SortedDictionary<string,object?>(StringComparer.Ordinal){["logical_path"]=logical,["path"]=inMirror?rel.Replace(Path.DirectorySeparatorChar,'/'):full.Replace(Path.DirectorySeparatorChar,'/'),["sha256"]=Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(full)))};
}).ToArray();
records=records.OrderBy(r=>(string)r["route"]!,StringComparer.Ordinal).ThenBy(r=>(string)r["action_method"]!,StringComparer.Ordinal).ThenBy(r=>(string)r["bound_member"]!,StringComparer.Ordinal).ToList();
sourceCallEdges=sourceCallEdges.OrderBy(r=>(string)r["route"]!,StringComparer.Ordinal).ThenBy(r=>(string)r["http_method"]!,StringComparer.Ordinal)
 .ThenBy(r=>(string)r["implementation_type"]!,StringComparer.Ordinal).ThenBy(r=>JsonSerializer.Serialize(r["call_site_source"]),StringComparer.Ordinal)
 .ThenBy(r=>(string)r["callee_method"]!,StringComparer.Ordinal).ToList();
var refs=compilation.References.OfType<PortableExecutableReference>().Select(r=>new SortedDictionary<string,object?>(StringComparer.Ordinal){["display"]=r.Display,["aliases"]=r.Properties.Aliases.OrderBy(x=>x,StringComparer.Ordinal).ToArray(),["embed_interop_types"]=r.Properties.EmbedInteropTypes,["kind"]=r.Properties.Kind.ToString(),["sha256"]=r.FilePath is not null && File.Exists(r.FilePath)?Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(r.FilePath))):null}).OrderBy(x=>x["display"]?.ToString(),StringComparer.Ordinal).ToArray();
string StableAssemblyPath(System.Reflection.Assembly assembly) {
 var name=Path.GetFileName(assembly.Location); var format=Path.Combine(sdk.MSBuildPath,"DotnetTools","dotnet-format");
 foreach(var candidate in new[]{Path.Combine(format,name),Path.Combine(format,"BuildHost-netcore",name)})
  if(File.Exists(candidate) && SHA256.HashData(File.ReadAllBytes(candidate)).SequenceEqual(SHA256.HashData(File.ReadAllBytes(assembly.Location)))) return candidate;
 throw new Exception("Roslyn/MSBuild tool assembly is outside the selected installed SDK: "+assembly.Location);
}
var toolAssemblies=AppDomain.CurrentDomain.GetAssemblies().Where(a=>!a.IsDynamic&&!string.IsNullOrEmpty(a.Location))
 .Select(a=>{try { var path=StableAssemblyPath(a); return new SortedDictionary<string,object?>(StringComparer.Ordinal){["name"]=a.GetName().Name,["path"]=path,["sha256"]=Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)))};} catch {return null;}})
 .Where(a=>a is not null).Cast<SortedDictionary<string,object?>>().GroupBy(a=>a["path"]?.ToString(),StringComparer.Ordinal).Select(g=>g.First()).OrderBy(a=>a["path"]?.ToString(),StringComparer.Ordinal).ToArray();
var buildHostPath=Path.Combine(sdk.MSBuildPath,"DotnetTools","dotnet-format","BuildHost-netcore");
var buildHostFiles=Directory.EnumerateFiles(buildHostPath,"*",SearchOption.AllDirectories).OrderBy(p=>p,StringComparer.Ordinal).Select(path=>new SortedDictionary<string,object?>(StringComparer.Ordinal){["path"]=Path.GetRelativePath(buildHostPath,path).Replace(Path.DirectorySeparatorChar,'/'),["sha256"]=Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)))}).ToArray();
var compilationOptions=(CSharpCompilationOptions)compilation.Options;
var semanticCompilationOptions=new SortedDictionary<string,object?>(StringComparer.Ordinal){
 ["output_kind"]=compilationOptions.OutputKind.ToString(),["optimization_level"]=compilationOptions.OptimizationLevel.ToString(),
 ["check_overflow"]=compilationOptions.CheckOverflow,["allow_unsafe"]=compilationOptions.AllowUnsafe,
 ["warning_level"]=compilationOptions.WarningLevel,["platform"]=compilationOptions.Platform.ToString(),
 ["nullable_context_options"]=compilationOptions.NullableContextOptions.ToString(),["general_diagnostic_option"]=compilationOptions.GeneralDiagnosticOption.ToString(),
 ["specific_diagnostic_options"]=new SortedDictionary<string,string>(compilationOptions.SpecificDiagnosticOptions.ToDictionary(kv=>kv.Key,kv=>kv.Value.ToString(),StringComparer.Ordinal),StringComparer.Ordinal),
 ["deterministic"]=compilationOptions.Deterministic,["concurrent_build"]=compilationOptions.ConcurrentBuild,
 ["metadata_import_options"]=compilationOptions.MetadataImportOptions.ToString(),["module_name"]=compilationOptions.ModuleName,
 ["usings"]=compilationOptions.Usings.OrderBy(x=>x,StringComparer.Ordinal).ToArray()
};
var semanticParseOptions=compilation.SyntaxTrees.OrderBy(t=>Path.GetFullPath(t.FilePath),StringComparer.Ordinal).Select(tree=>{
 var parse=(CSharpParseOptions)tree.Options;
 return new SortedDictionary<string,object?>(StringComparer.Ordinal){["path"]=CanonicalPath(mirrorRoot,repositoryRoot,tree.FilePath),["language_version"]=parse.LanguageVersion.ToString(),["source_code_kind"]=parse.Kind.ToString(),["documentation_mode"]=parse.DocumentationMode.ToString(),["preprocessor_symbols"]=parse.PreprocessorSymbolNames.OrderBy(x=>x,StringComparer.Ordinal).ToArray(),["features"]=new SortedDictionary<string,string>(parse.Features.ToDictionary(kv=>kv.Key,kv=>kv.Value,StringComparer.Ordinal),StringComparer.Ordinal)};
}).ToArray();
string StableDiagnostic(string value) => value.Replace(mirrorRoot+Path.DirectorySeparatorChar,"repo/",StringComparison.Ordinal).Replace(mirrorRoot,"repo",StringComparison.Ordinal);
sourceCallEdges=sourceCallEdges.OrderBy(edge=>edge["route"]!.ToString(),StringComparer.Ordinal).ThenBy(edge=>edge["http_method"]!.ToString(),StringComparer.Ordinal).ThenBy(edge=>edge["implementation_type"]!.ToString(),StringComparer.Ordinal).ThenBy(edge=>edge["call_site_source"]!.ToString(),StringComparer.Ordinal).ToList();
sourceCallUnresolved=sourceCallUnresolved.OrderBy(edge=>edge["route"]!.ToString(),StringComparer.Ordinal).ThenBy(edge=>edge["http_method"]!.ToString(),StringComparer.Ordinal).ThenBy(edge=>edge["source"]!.ToString(),StringComparer.Ordinal).ToList();
var output=new SortedDictionary<string,object?>(StringComparer.Ordinal){["relationships"]=records,["unresolved"]=unresolved.OrderBy(x=>x["source"]?.ToString(),StringComparer.Ordinal).ToArray(),["source_call_graph"]=sourceCallGraph,["source_call_edges"]=sourceCallEdges,["source_call_unresolved"]=sourceCallUnresolved,["references"]=refs,["imports"]=imports,["toolchain_assemblies"]=toolAssemblies,["build_host_files"]=buildHostFiles,["compiler_errors"]=errors,["compiler_warnings"]=diagnostics.Where(d=>d.Severity==DiagnosticSeverity.Warning).Select(d=>StableDiagnostic(d.ToString())).OrderBy(x=>x,StringComparer.Ordinal).ToArray(),["workspace_diagnostics"]=workspaceDiagnostics.Select(StableDiagnostic).OrderBy(x=>x,StringComparer.Ordinal).ToArray(),["sdk_path"]=sdk.MSBuildPath,["roslyn_version"]=typeof(Compilation).Assembly.GetName().Version?.ToString(),["language_version"]=((CSharpParseOptions)compilation.SyntaxTrees.First().Options).LanguageVersion.ToString(),["target_framework"]=framework,["source_trees"]=compilation.SyntaxTrees.Count(),["compilation_options"]=semanticCompilationOptions,["parse_options"]=semanticParseOptions};
var outputJson=JsonSerializer.Serialize(output,new JsonSerializerOptions{WriteIndented=true});
if(System.Text.Encoding.UTF8.GetByteCount(outputJson)>MaxSourceCallGraphBytes) throw new Exception("source-call extractor output cap exceeded; no partial graph emitted");
Console.WriteLine(outputJson);
