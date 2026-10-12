import { Component, signal } from '@angular/core';
import { EmptyStateComponent } from '../shared/empty-state.component';
import { SkeletonComponent } from '../shared/skeleton.component';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [EmptyStateComponent, SkeletonComponent],
  templateUrl: './home.component.html',
})
export class HomeComponent {
  readonly loading = signal(true);
  readonly tables = signal<string[]>([]);
}
