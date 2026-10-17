// expect: none
@Composable
fun Card() {
    Box(Modifier.clip(RoundedCornerShape(50)).padding(16.dp))
}
