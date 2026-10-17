// expect: none
import SwiftUI
struct Banner: View {
    // Color(red: 1, green: 0, blue: 0) in a comment is fine
    var body: some View { Text("Saved").foregroundStyle(DemoColor.primary).padding(16) }
}
