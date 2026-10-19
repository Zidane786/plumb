struct Toolbar: View {
    var body: some View {
        HStack {
            Button(action: close) {
                Image(systemName: "xmark")
            }
            .frame(width: 28, height: 28)
            Image(systemName: "star")
                .frame(width: 20, height: 20)
        }
    }
}
