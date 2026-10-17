import { Component, signal } from '@angular/core';

@Component({
  selector: 'app-notes',
  standalone: true,
  templateUrl: './notes.component.html',
  styleUrl: './notes.component.scss',
})
export class NotesComponent {
  readonly notes = signal<string[]>(['Buy stamps', 'Book the venue']);
}
