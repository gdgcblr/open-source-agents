import { Component, OnInit, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { CurrentUserService, DEMO_PERSONAS } from './core/services/current-user.service';
import { ProfileStore } from './core/services/profile-store.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent implements OnInit {
  private readonly currentUser = inject(CurrentUserService);
  protected readonly profileStore = inject(ProfileStore);

  protected readonly personas = DEMO_PERSONAS;
  protected readonly currentUserId = this.currentUser.userId;

  ngOnInit(): void {
    this.profileStore.load();
  }

  onPersonaChange(userId: string): void {
    this.currentUser.setUserId(userId);
    this.profileStore.load();
  }
}
