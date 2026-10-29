import * as Sharing from 'expo-sharing';

/** Opens the native share sheet (AirDrop, Save to Files, messaging apps…). */
export async function shareFile(uri: string, mimeType: string, title?: string | null): Promise<boolean> {
  if (!(await Sharing.isAvailableAsync())) return false;
  await Sharing.shareAsync(uri, { mimeType, dialogTitle: title ?? 'Share media' });
  return true;
}
