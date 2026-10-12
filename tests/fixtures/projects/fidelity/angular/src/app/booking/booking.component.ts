import { Component } from '@angular/core';
import { NgIf, NgTemplateOutlet } from '@angular/common';

@Component({
  selector: 'app-booking',
  standalone: true,
  imports: [NgIf, NgTemplateOutlet],
  templateUrl: './booking.component.html',
})
export class BookingComponent {
  inFlight = false;
  problem: string | null = null;

  save(): void {
    this.inFlight = true;
  }
}
