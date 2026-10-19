import { Routes } from '@angular/router';
import { NotesComponent } from './notes/notes.component';

export const routes: Routes = [
  { path: '', component: NotesComponent },
  {
    path: 'settings',
    loadComponent: () => import('./settings/settings.component').then((m) => m.SettingsComponent),
  },
  { path: '**', redirectTo: '' },
];
