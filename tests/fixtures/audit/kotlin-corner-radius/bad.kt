// expect: kotlin-corner-radius@4
@Composable
fun Card() {
    Box(Modifier.clip(RoundedCornerShape(12.dp)))
}
