using OpenRA;

var resources = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "Resources"));
var support = Path.Combine(
    Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
    "Library", "Application Support", "OpenRA AI", "RA2 Preview");
Directory.CreateDirectory(support);
var defaults = new[]
{
    $"Engine.EngineDir={resources}",
    $"Engine.SupportDir={support}",
    "Game.Mod=ra2",
    "Graphics.Mode=Windowed",
    "Graphics.WindowedSize=1280,800",
};

try
{
    return (int)Game.InitializeAndRun(defaults.Concat(args).ToArray());
}
catch (Exception exception)
{
    File.WriteAllText(Path.Combine(support, "launcher-error.log"), exception.ToString());
    Console.Error.WriteLine(exception);
    return 1;
}
finally
{
    Log.Dispose();
}
