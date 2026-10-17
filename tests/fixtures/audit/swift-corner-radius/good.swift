// expect: none
import SwiftUI
struct Card: View {
    var body: some View { Text("Hi").clipShape(RoundedRectangle(cornerRadius: DemoRadius.md)).cornerRadius(0) }
}
