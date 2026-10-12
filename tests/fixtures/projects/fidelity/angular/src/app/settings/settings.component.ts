import { Component } from '@angular/core';

@Component({
  selector: 'app-settings',
  standalone: true,
  template: `
    <h1>Réglages</h1>
    @if (saveFailed) {
      <p role="alert">Les réglages n’ont pas été enregistrés</p>
    }
    <button type="button" (click)="save()">Enregistrer</button>
  `,
})
export class SettingsComponent {
  saveFailed = false;

  save(): void {
    this.saveFailed = false;
  }
}
