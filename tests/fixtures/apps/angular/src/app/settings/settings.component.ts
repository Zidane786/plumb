import { Component } from '@angular/core';

@Component({
  selector: 'app-settings',
  standalone: true,
  template: `
    <h1>Settings</h1>
    <button type="button" class="save">Save</button>
  `,
  styleUrl: './settings.component.scss',
})
export class SettingsComponent {}
