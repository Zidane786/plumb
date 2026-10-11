import styles from "./button.module.css";
export function Button(props: any) {
  return <button className={styles.root} {...props} />;
}
