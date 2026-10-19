import SwiftUI

struct HabitListView: View {
    let habits = ["Walk", "Read"]

    var body: some View {
        NavigationStack {
            List(habits, id: \.self) { habit in
                Text(habit)
                    .font(.system(size: 15))
                    .foregroundStyle(Color(red: 0.12, green: 0.48, blue: 0.55))
            }
            .navigationTitle("Habits")
        }
    }
}
