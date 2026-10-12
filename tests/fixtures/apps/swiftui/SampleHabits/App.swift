import SwiftUI

@main
struct SampleHabitsApp: App {
    var body: some Scene {
        WindowGroup {
            TabView {
                HabitListView()
                    .tabItem { Label("Habits", systemImage: "house") }
                SettingsView()
                    .tabItem { Label("Settings", systemImage: "gearshape") }
            }
        }
    }
}
