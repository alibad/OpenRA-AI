#import <Cocoa/Cocoa.h>

@interface OpenRAAIAppDelegate : NSObject <NSApplicationDelegate>
@property(nonatomic, retain) NSTask *wrapperTask;
@end

@implementation OpenRAAIAppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
	NSString *wrapper = [[[NSBundle mainBundle] bundlePath] stringByAppendingPathComponent:@"Contents/MacOS/OpenRAAI.sh"];
	if (wrapper == nil)
		exit(1);

	NSMutableArray *arguments = [NSMutableArray arrayWithObject:wrapper];
	NSArray *processArguments = [[NSProcessInfo processInfo] arguments];
	if ([processArguments count] > 1)
		[arguments addObjectsFromArray:[processArguments subarrayWithRange:NSMakeRange(1, [processArguments count] - 1)]];

	self.wrapperTask = [[[NSTask alloc] init] autorelease];
	[self.wrapperTask setLaunchPath:@"/bin/bash"];
	[self.wrapperTask setArguments:arguments];
	[[NSNotificationCenter defaultCenter]
		addObserver:self
		selector:@selector(wrapperExited:)
		name:NSTaskDidTerminateNotification
		object:self.wrapperTask];
	[self.wrapperTask launch];
}

- (void)wrapperExited:(NSNotification *)notification
{
	exit([self.wrapperTask terminationStatus]);
}

- (void)applicationWillTerminate:(NSNotification *)notification
{
	if ([self.wrapperTask isRunning])
		[self.wrapperTask terminate];
}

- (void)dealloc
{
	[[NSNotificationCenter defaultCenter] removeObserver:self];
	[_wrapperTask release];
	[super dealloc];
}

@end

int main(int argc, const char *argv[])
{
	NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
	NSApplication *application = [NSApplication sharedApplication];
	OpenRAAIAppDelegate *delegate = [[OpenRAAIAppDelegate alloc] init];
	[application setDelegate:delegate];
	[application run];
	[delegate release];
	[pool drain];
	return 0;
}
