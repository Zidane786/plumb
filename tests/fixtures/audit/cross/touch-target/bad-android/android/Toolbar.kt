@Composable
fun Toolbar() {
    Row {
        Icon(Icons.Default.Close, null, modifier = Modifier.size(32.dp).clickable { close() })
        IconButton(onClick = {}, modifier = Modifier.size(36.dp)) { Icon(Icons.Default.Star, null) }
        Icon(Icons.Default.Info, null, modifier = Modifier.size(16.dp))
    }
}
