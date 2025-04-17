import { Component } from '@angular/core';

@Component({
  selector: 'app-file-upload',
  templateUrl: './file-upload.component.html',
  styleUrls: ['./file-upload.component.scss']
})
export class FileUploadComponent {
  
  onFileSelected(event: any) {
    const file: File = event.target.files[0];
    if (file) {
      // Lógica para upload do arquivo
      console.log('Arquivo selecionado:', file.name);
    }
  }
}
