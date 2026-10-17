struct Toolbar: View {
    var body: some View {
        HStack {
            Button(action: close) {
                Image(systemName: "xmark")
            }
            .frame(minWidth: 44, minHeight: 44)
            Image(systemName: "star")
                .frame(width: 20, height: 20)
        }
    }
}
