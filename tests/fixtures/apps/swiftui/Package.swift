// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "SampleHabits",
    platforms: [.iOS(.v17)],
    targets: [
        .executableTarget(name: "SampleHabits", path: "SampleHabits")
    ]
)
