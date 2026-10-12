import SwiftUI

struct SettingsView: View {
    @State private var reminders = true

    var body: some View {
        VStack(alignment: .leading) {
            Toggle("Daily reminders", isOn: $reminders)
            Button("Save") {}
                .padding()
                .background(Color.accentColor)
                .clipShape(RoundedRectangle(cornerRadius: 6))
        }
        .padding()
    }
}
