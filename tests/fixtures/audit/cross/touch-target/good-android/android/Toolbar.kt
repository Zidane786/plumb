@Composable
fun Toolbar() {
    Row {
        Icon(Icons.Default.Close, null, modifier = Modifier.size(48.dp).clickable { close() })
        IconButton(onClick = {}, modifier = Modifier.defaultMinSize(minWidth = 48.dp, minHeight = 48.dp)) { Icon(Icons.Default.Star, null) }
        Icon(Icons.Default.Info, null, modifier = Modifier.size(16.dp))
    }
}
